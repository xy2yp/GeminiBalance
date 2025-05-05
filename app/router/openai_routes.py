from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.config.config import settings
from app.core.security import SecurityService
from app.domain.openai_models import (
    ChatRequest,
    EmbeddingRequest,
    ImageGenerationRequest,
)
from app.handler.retry_handler import RetryHandler
from app.handler.error_handler import handle_route_errors # 导入共享错误处理器
from app.log.logger import get_openai_logger
from app.service.chat.openai_chat_service import OpenAIChatService
from app.service.embedding.embedding_service import EmbeddingService
from app.service.image.image_create_service import ImageCreateService
from app.service.key.key_manager import KeyManager, get_key_manager_instance
from app.service.model.model_service import ModelService

router = APIRouter()
logger = get_openai_logger()

# 初始化服务
security_service = SecurityService()
model_service = ModelService()
embedding_service = EmbeddingService()
image_create_service = ImageCreateService()


async def get_key_manager():
    return await get_key_manager_instance()


async def get_next_working_key_wrapper(
    key_manager: KeyManager = Depends(get_key_manager),
):
    return await key_manager.get_next_working_key()


async def get_openai_chat_service(key_manager: KeyManager = Depends(get_key_manager)):
    """获取OpenAI聊天服务实例"""
    return OpenAIChatService(settings.BASE_URL, key_manager)


@router.get("/v1/models")
@router.get("/hf/v1/models")
async def list_models(
    _=Depends(security_service.verify_authorization),
    key_manager: KeyManager = Depends(get_key_manager),
):
    """获取可用的 OpenAI 模型列表 (兼容 Gemini 和 OpenAI)。"""
    operation_name = "list_models"
    async with handle_route_errors(logger, operation_name):
        logger.info("Handling models list request")
        api_key = await key_manager.get_first_valid_key()
        logger.info(f"Using API key: {api_key}")
        return await model_service.get_gemini_openai_models(api_key)


@router.post("/v1/chat/completions")
@router.post("/hf/v1/chat/completions")
@RetryHandler(max_retries=settings.MAX_RETRIES, key_arg="api_key")
async def chat_completion(
    request: ChatRequest,
    _=Depends(security_service.verify_authorization),
    api_key: str = Depends(get_next_working_key_wrapper),
    key_manager: KeyManager = Depends(get_key_manager), # 保留 key_manager 用于获取 paid_key
    chat_service: OpenAIChatService = Depends(get_openai_chat_service),
):
    """处理 OpenAI 聊天补全请求，支持流式响应和特定模型切换。"""
    operation_name = "chat_completion"
    # 检查是否为图像生成相关的聊天模型
    is_image_chat = request.model == f"{settings.CREATE_IMAGE_MODEL}-chat"
    current_api_key = api_key # 保存原始 key
    if is_image_chat:
        current_api_key = await key_manager.get_paid_key() # 获取付费密钥

    async with handle_route_errors(logger, operation_name):
        logger.info(f"Handling chat completion request for model: {request.model}")
        logger.debug(f"Request: \n{request.model_dump_json(indent=2)}")
        logger.info(f"Using API key: {current_api_key}")

        # 检查模型支持性应在错误处理块内，以便捕获并记录错误
        if not await model_service.check_model_support(request.model):
            # 使用 HTTPException，会被 handle_route_errors 捕获并记录
            raise HTTPException(
                status_code=400, detail=f"Model {request.model} is not supported"
            )

        if is_image_chat:
            # 图像生成聊天
            response = await chat_service.create_image_chat_completion(request, current_api_key)
            # 处理流式响应
            if request.stream:
                return StreamingResponse(response, media_type="text/event-stream")
            # 非流式直接返回结果
            return response
        else:
            # 普通聊天补全
            response = await chat_service.create_chat_completion(request, current_api_key)
            # 处理流式响应
            if request.stream:
                return StreamingResponse(response, media_type="text/event-stream")
            # 非流式直接返回结果
            return response


@router.post("/v1/images/generations")
@router.post("/hf/v1/images/generations")
async def generate_image(
    request: ImageGenerationRequest,
    _=Depends(security_service.verify_authorization),
):
    """处理 OpenAI 图像生成请求。"""
    operation_name = "generate_image"
    async with handle_route_errors(logger, operation_name):
        logger.info(f"Handling image generation request for prompt: {request.prompt}")
        response = image_create_service.generate_images(request)
        return response


@router.post("/v1/embeddings")
@router.post("/hf/v1/embeddings")
async def embedding(
    request: EmbeddingRequest,
    _=Depends(security_service.verify_authorization),
    key_manager: KeyManager = Depends(get_key_manager),
):
    """处理 OpenAI 文本嵌入请求。"""
    operation_name = "embedding"
    async with handle_route_errors(logger, operation_name):
        logger.info(f"Handling embedding request for model: {request.model}")
        api_key = await key_manager.get_next_working_key()
        logger.info(f"Using API key: {api_key}")
        response = await embedding_service.create_embedding(
            input_text=request.input, model=request.model, api_key=api_key
        )
        return response


@router.get("/v1/keys/list")
@router.get("/hf/v1/keys/list")
async def get_keys_list(
    _=Depends(security_service.verify_auth_token),
    key_manager: KeyManager = Depends(get_key_manager),
):
    """获取有效和无效的API key列表 (需要管理 Token 认证)。"""
    operation_name = "get_keys_list"
    async with handle_route_errors(logger, operation_name):
        logger.info("Handling keys list request")
        keys_status = await key_manager.get_keys_by_status()
        return {
            "status": "success",
            "data": {
                "valid_keys": keys_status["valid_keys"],
                "invalid_keys": keys_status["invalid_keys"],
            },
            "total": len(keys_status["valid_keys"]) + len(keys_status["invalid_keys"]),
        }
