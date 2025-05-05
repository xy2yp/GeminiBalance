from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.config.config import settings
from app.core.security import SecurityService
from app.domain.openai_models import (
    ChatRequest,
    EmbeddingRequest,
    ImageGenerationRequest,
)
from app.handler.retry_handler import RetryHandler
from app.handler.error_handler import handle_route_errors
from app.log.logger import get_openai_compatible_logger
from app.service.key.key_manager import KeyManager, get_key_manager_instance
from app.service.openai_compatiable.openai_compatiable_service import OpenAICompatiableService


router = APIRouter()
logger = get_openai_compatible_logger()

# 初始化服务
security_service = SecurityService()

async def get_key_manager():
    return await get_key_manager_instance()


async def get_next_working_key_wrapper(
    key_manager: KeyManager = Depends(get_key_manager),
):
    return await key_manager.get_next_working_key()


async def get_openai_service(key_manager: KeyManager = Depends(get_key_manager)):
    """获取OpenAI聊天服务实例"""
    return OpenAICompatiableService(settings.BASE_URL, key_manager)


@router.get("/openai/v1/models")
async def list_models(
    _=Depends(security_service.verify_authorization),
    key_manager: KeyManager = Depends(get_key_manager),
    openai_service: OpenAICompatiableService = Depends(get_openai_service),
):
    """获取可用模型列表。"""
    operation_name = "list_models"
    async with handle_route_errors(logger, operation_name):
        logger.info("Handling models list request")
        api_key = await key_manager.get_first_valid_key()
        logger.info(f"Using API key: {api_key}")
        return await openai_service.get_models(api_key)


@router.post("/openai/v1/chat/completions")
@RetryHandler(max_retries=settings.MAX_RETRIES, key_arg="api_key")
async def chat_completion(
    request: ChatRequest,
    _=Depends(security_service.verify_authorization),
    api_key: str = Depends(get_next_working_key_wrapper),
    key_manager: KeyManager = Depends(get_key_manager),
    openai_service: OpenAICompatiableService = Depends(get_openai_service),
):
    """处理聊天补全请求，支持流式响应和特定模型切换。"""
    operation_name = "chat_completion"
    # 检查是否为图像生成相关的聊天模型，如果是，则使用付费密钥
    is_image_chat = request.model == f"{settings.CREATE_IMAGE_MODEL}-chat"
    current_api_key = api_key # 保存原始key（可能是普通key）
    if is_image_chat:
        current_api_key = await key_manager.get_paid_key() # 获取付费密钥

    async with handle_route_errors(logger, operation_name):
        logger.info(f"Handling chat completion request for model: {request.model}")
        logger.debug(f"Request: \n{request.model_dump_json(indent=2)}")
        logger.info(f"Using API key: {current_api_key}") # 使用 current_api_key

        if is_image_chat:
            # 图像生成聊天，调用特定服务，不处理流式
            response = await openai_service.create_image_chat_completion(request, current_api_key)
            return response # 直接返回结果
        else:
            # 普通聊天补全
            response = await openai_service.create_chat_completion(request, current_api_key)
            # 处理流式响应
            if request.stream:
                 # 假设 openai_service.create_chat_completion 在流式时返回异步生成器
                return StreamingResponse(response, media_type="text/event-stream")
            # 非流式直接返回结果
            return response


@router.post("/openai/v1/images/generations")
async def generate_image(
    request: ImageGenerationRequest,
    _=Depends(security_service.verify_authorization),
    openai_service: OpenAICompatiableService = Depends(get_openai_service),
):
    """处理图像生成请求。"""
    operation_name = "generate_image"
    async with handle_route_errors(logger, operation_name):
        logger.info(f"Handling image generation request for prompt: {request.prompt}")
        # 强制使用配置的模型，确保请求中包含正确的模型信息
        request.model = settings.CREATE_IMAGE_MODEL
        return await openai_service.generate_images(request)


@router.post("/openai/v1/embeddings")
async def embedding(
    request: EmbeddingRequest,
    _=Depends(security_service.verify_authorization),
    key_manager: KeyManager = Depends(get_key_manager),
    openai_service: OpenAICompatiableService = Depends(get_openai_service),
):
    """处理文本嵌入请求。"""
    operation_name = "embedding"
    async with handle_route_errors(logger, operation_name):
        logger.info(f"Handling embedding request for model: {request.model}")
        api_key = await key_manager.get_next_working_key()
        logger.info(f"Using API key: {api_key}")
        return await openai_service.create_embeddings(
            input_text=request.input, model=request.model, api_key=api_key
        )
