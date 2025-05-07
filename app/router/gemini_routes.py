from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from copy import deepcopy
import asyncio
from app.config.config import settings
from app.log.logger import get_gemini_logger
from app.core.security import SecurityService
from app.domain.gemini_models import GeminiContent, GeminiRequest, ResetSelectedKeysRequest, VerifySelectedKeysRequest # 添加导入
from app.service.chat.gemini_chat_service import GeminiChatService
from app.service.key.key_manager import KeyManager, get_key_manager_instance
from app.service.model.model_service import ModelService
from app.handler.retry_handler import RetryHandler
from app.handler.error_handler import handle_route_errors
from app.core.constants import API_VERSION

# 路由设置
router = APIRouter(prefix=f"/gemini/{API_VERSION}")
router_v1beta = APIRouter(prefix=f"/{API_VERSION}")
logger = get_gemini_logger()

# 初始化服务
security_service = SecurityService()
model_service = ModelService()


async def get_key_manager():
    """获取密钥管理器实例"""
    return await get_key_manager_instance()


async def get_next_working_key(key_manager: KeyManager = Depends(get_key_manager)):
    """获取下一个可用的API密钥"""
    return await key_manager.get_next_working_key()


async def get_chat_service(key_manager: KeyManager = Depends(get_key_manager)):
    """获取Gemini聊天服务实例"""
    return GeminiChatService(settings.BASE_URL, key_manager)


@router.get("/models")
@router_v1beta.get("/models")
async def list_models(
    _=Depends(security_service.verify_key_or_goog_api_key),
    key_manager: KeyManager = Depends(get_key_manager)
):
    """获取可用的 Gemini 模型列表，并根据配置添加衍生模型（搜索、图像、非思考）。"""
    operation_name = "list_gemini_models"
    logger.info("-" * 50 + operation_name + "-" * 50)
    logger.info("Handling Gemini models list request")

    try:
        api_key = await key_manager.get_first_valid_key()
        if not api_key:
             raise HTTPException(status_code=503, detail="No valid API keys available to fetch models.")
        logger.info(f"Using API key: {api_key}")

        models_data =await model_service.get_gemini_models(api_key)
        if not models_data or "models" not in models_data:
             raise HTTPException(status_code=500, detail="Failed to fetch base models list.")

        models_json = deepcopy(models_data) # 操作副本以防修改原始缓存
        model_mapping = {x.get("name", "").split("/", maxsplit=1)[-1]: x for x in models_json.get("models", [])}

        def add_derived_model(base_name, suffix, display_suffix):
            model = model_mapping.get(base_name)
            if not model:
                logger.warning(f"Base model '{base_name}' not found for derived model '{suffix}'.")
                return
            item = deepcopy(model)
            item["name"] = f"models/{base_name}{suffix}"
            display_name = f'{item.get("displayName", base_name)}{display_suffix}'
            item["displayName"] = display_name
            item["description"] = display_name
            models_json["models"].append(item)

        # 添加衍生模型
        if settings.SEARCH_MODELS:
            for name in settings.SEARCH_MODELS:
                add_derived_model(name, "-search", " For Search")
        if settings.IMAGE_MODELS:
            for name in settings.IMAGE_MODELS:
                 add_derived_model(name, "-image", " For Image")
        if settings.THINKING_MODELS:
            for name in settings.THINKING_MODELS:
                add_derived_model(name, "-non-thinking", " Non Thinking")

        logger.info("Gemini models list request successful")
        return models_json
    except HTTPException as http_exc:
        # 重新抛出已知的 HTTP 异常
        raise http_exc
    except Exception as e:
        logger.error(f"Error getting Gemini models list: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Internal server error while fetching Gemini models list"
        ) from e


@router.post("/models/{model_name}:generateContent")
@router_v1beta.post("/models/{model_name}:generateContent")
@RetryHandler(key_arg="api_key")
async def generate_content(
    model_name: str,
    request: GeminiRequest,
    _=Depends(security_service.verify_key_or_goog_api_key),
    api_key: str = Depends(get_next_working_key),
    key_manager: KeyManager = Depends(get_key_manager),
    chat_service: GeminiChatService = Depends(get_chat_service)
):
    """处理 Gemini 非流式内容生成请求。"""
    operation_name = "gemini_generate_content"
    async with handle_route_errors(logger, operation_name, failure_message="Content generation failed"):
        logger.info(f"Handling Gemini content generation request for model: {model_name}")
        logger.debug(f"Request: \n{request.model_dump_json(indent=2)}")
        logger.info(f"Using API key: {api_key}")

        if not await model_service.check_model_support(model_name):
            raise HTTPException(status_code=400, detail=f"Model {model_name} is not supported")

        response = await chat_service.generate_content(
            model=model_name,
            request=request,
            api_key=api_key
        )
        return response


@router.post("/models/{model_name}:streamGenerateContent")
@router_v1beta.post("/models/{model_name}:streamGenerateContent")
@RetryHandler(key_arg="api_key")
async def stream_generate_content(
    model_name: str,
    request: GeminiRequest,
    _=Depends(security_service.verify_key_or_goog_api_key),
    api_key: str = Depends(get_next_working_key),
    key_manager: KeyManager = Depends(get_key_manager),
    chat_service: GeminiChatService = Depends(get_chat_service)
):
    """处理 Gemini 流式内容生成请求。"""
    operation_name = "gemini_stream_generate_content"
    # 流式请求的成功/失败日志在流处理中更复杂，这里仅用上下文管理器处理启动错误
    async with handle_route_errors(logger, operation_name, failure_message="Streaming request initiation failed"):
        logger.info(f"Handling Gemini streaming content generation for model: {model_name}")
        logger.debug(f"Request: \n{request.model_dump_json(indent=2)}")
        logger.info(f"Using API key: {api_key}")

        if not await model_service.check_model_support(model_name):
            raise HTTPException(status_code=400, detail=f"Model {model_name} is not supported")

        response_stream = chat_service.stream_generate_content(
            model=model_name,
            request=request,
            api_key=api_key
        )
        # 注意：流本身的错误需要在服务层或流迭代中处理，这里只返回流响应
        return StreamingResponse(response_stream, media_type="text/event-stream")


@router.post("/reset-all-fail-counts")
async def reset_all_key_fail_counts(key_type: str = None, key_manager: KeyManager = Depends(get_key_manager)):
    """批量重置Gemini API密钥的失败计数，可选择性地仅重置有效或无效密钥"""
    logger.info("-" * 50 + "reset_all_gemini_key_fail_counts" + "-" * 50)
    logger.info(f"Received reset request with key_type: {key_type}")
    
    try:
        # 获取分类后的密钥
        keys_by_status = await key_manager.get_keys_by_status()
        valid_keys = keys_by_status.get("valid_keys", {})
        invalid_keys = keys_by_status.get("invalid_keys", {})
        
        # 根据类型选择要重置的密钥
        keys_to_reset = []
        if key_type == "valid":
            keys_to_reset = list(valid_keys.keys())
            logger.info(f"Resetting only valid keys, count: {len(keys_to_reset)}")
        elif key_type == "invalid":
            keys_to_reset = list(invalid_keys.keys())
            logger.info(f"Resetting only invalid keys, count: {len(keys_to_reset)}")
        else:
            # 重置所有密钥
            await key_manager.reset_failure_counts()
            return JSONResponse({"success": True, "message": "所有密钥的失败计数已重置"})
        
        # 批量重置指定类型的密钥
        for key in keys_to_reset:
            await key_manager.reset_key_failure_count(key)
        
        return JSONResponse({
            "success": True,
            "message": f"{key_type}密钥的失败计数已重置",
            "reset_count": len(keys_to_reset)
        })
    except Exception as e:
        logger.error(f"Failed to reset key failure counts: {str(e)}")
        return JSONResponse({"success": False, "message": f"批量重置失败: {str(e)}"}, status_code=500)
    
    
@router.post("/reset-selected-fail-counts")
async def reset_selected_key_fail_counts(
    request: ResetSelectedKeysRequest,
    key_manager: KeyManager = Depends(get_key_manager)
):
    """批量重置选定Gemini API密钥的失败计数"""
    logger.info("-" * 50 + "reset_selected_gemini_key_fail_counts" + "-" * 50)
    keys_to_reset = request.keys
    key_type = request.key_type # 获取类型用于日志记录和响应消息
    logger.info(f"Received reset request for {len(keys_to_reset)} selected {key_type} keys.")

    if not keys_to_reset:
        return JSONResponse({"success": False, "message": "没有提供需要重置的密钥"}, status_code=400)

    reset_count = 0
    errors = []

    try:
        for key in keys_to_reset:
            try:
                result = await key_manager.reset_key_failure_count(key)
                if result:
                    reset_count += 1
                else:
                    # 记录未找到的密钥，但不视为致命错误
                    logger.warning(f"Key not found during selective reset: {key}")
            except Exception as key_error:
                # 记录单个密钥重置时的错误
                logger.error(f"Error resetting key {key}: {str(key_error)}")
                errors.append(f"Key {key}: {str(key_error)}")

        if errors:
             # 如果有错误，报告部分成功或完全失败
             error_message = f"批量重置完成，但出现错误: {'; '.join(errors)}"
             # 确定最终状态码和成功标志
             final_success = reset_count > 0
             status_code = 207 if final_success and errors else 500 # 207 Multi-Status if partially successful, 500 if completely failed
             return JSONResponse({
                 "success": final_success,
                 "message": error_message,
                 "reset_count": reset_count
             }, status_code=status_code)

        # 完全成功的情况
        return JSONResponse({
            "success": True,
            "message": f"成功重置 {reset_count} 个选定 {key_type} 密钥的失败计数",
            "reset_count": reset_count
        })
    except Exception as e:
        # 捕获循环外的意外错误
        logger.error(f"Failed to process reset selected key failure counts request: {str(e)}")
        return JSONResponse({"success": False, "message": f"批量重置处理失败: {str(e)}"}, status_code=500)


@router.post("/reset-fail-count/{api_key}")
async def reset_key_fail_count(api_key: str, key_manager: KeyManager = Depends(get_key_manager)):
    """重置指定Gemini API密钥的失败计数"""
    logger.info("-" * 50 + "reset_gemini_key_fail_count" + "-" * 50)
    logger.info(f"Resetting failure count for API key: {api_key}")
    
    try:
        result = await key_manager.reset_key_failure_count(api_key)
        if result:
            return JSONResponse({"success": True, "message": "失败计数已重置"})
        return JSONResponse({"success": False, "message": "未找到指定密钥"}, status_code=404)
    except Exception as e:
        logger.error(f"Failed to reset key failure count: {str(e)}")
        return JSONResponse({"success": False, "message": f"重置失败: {str(e)}"}, status_code=500)


@router.post("/verify-key/{api_key}")
async def verify_key(api_key: str, chat_service: GeminiChatService = Depends(get_chat_service), key_manager: KeyManager = Depends(get_key_manager)):
    """验证Gemini API密钥的有效性"""
    logger.info("-" * 50 + "verify_gemini_key" + "-" * 50)
    logger.info("Verifying API key validity")
    
    try:
        # 使用generate_content接口测试key的有效性
        gemini_request = GeminiRequest(
            contents=[
                GeminiContent(
                    role="user",
                    parts=[{"text": "hi"}],
                )
            ],
            generation_config={"temperature": 0.7, "top_p": 1.0, "max_output_tokens": 10}
        )
        
        response = await chat_service.generate_content(
            settings.TEST_MODEL,
            gemini_request,
            api_key
        )
        
        if response:
            return JSONResponse({"status": "valid"})        
    except Exception as e:
        logger.error(f"Key verification failed: {str(e)}")
        
        # 验证出现异常时增加失败计数
        async with key_manager.failure_count_lock:
            if api_key in key_manager.key_failure_counts:
                key_manager.key_failure_counts[api_key] += 1
                logger.warning(f"Verification exception for key: {api_key}, incrementing failure count")
        
        return JSONResponse({"status": "invalid", "error": str(e)})


@router.post("/verify-selected-keys")
async def verify_selected_keys(
    request: VerifySelectedKeysRequest,
    chat_service: GeminiChatService = Depends(get_chat_service),
    key_manager: KeyManager = Depends(get_key_manager)
):
    """批量验证选定Gemini API密钥的有效性"""
    logger.info("-" * 50 + "verify_selected_gemini_keys" + "-" * 50)
    keys_to_verify = request.keys
    logger.info(f"Received verification request for {len(keys_to_verify)} selected keys.")

    if not keys_to_verify:
        return JSONResponse({"success": False, "message": "没有提供需要验证的密钥"}, status_code=400)

    successful_keys = []
    failed_keys = {} # 存储失败的 key 和错误信息

    async def _verify_single_key(api_key: str):
        """内部函数，用于验证单个密钥并处理异常"""
        nonlocal successful_keys, failed_keys # 允许修改外部列表和字典
        try:
            # 重用单密钥验证逻辑的核心部分
            gemini_request = GeminiRequest(
                contents=[GeminiContent(role="user", parts=[{"text": "hi"}])]
            )
            # 注意：这里直接调用 chat_service.generate_content，不依赖于 key_manager 获取密钥
            await chat_service.generate_content(
                settings.TEST_MODEL,
                gemini_request,
                api_key
            )
            # 如果上面没有抛出异常，则认为密钥有效
            successful_keys.append(api_key)
            return api_key, "valid", None
        except Exception as e:
            error_message = str(e)
            logger.warning(f"Key verification failed for {api_key}: {error_message}")
            # 验证失败时增加失败计数 (使用与 /verify-key 一致的逻辑)
            async with key_manager.failure_count_lock:
                if api_key in key_manager.key_failure_counts:
                    key_manager.key_failure_counts[api_key] += 1
                    logger.warning(f"Bulk verification exception for key: {api_key}, incrementing failure count")
                else:
                     # 如果密钥不在计数中（可能刚添加或从未失败），初始化为1
                     key_manager.key_failure_counts[api_key] = 1
                     logger.warning(f"Bulk verification exception for key: {api_key}, initializing failure count to 1")
            failed_keys[api_key] = error_message # 记录失败的 key 和错误信息
            return api_key, "invalid", error_message

    # 并发执行所有密钥的验证
    tasks = [_verify_single_key(key) for key in keys_to_verify]
    results = await asyncio.gather(*tasks, return_exceptions=True) # return_exceptions=True 捕获任务本身的异常

    # 处理并发执行的结果
    for result in results:
        if isinstance(result, Exception):
            # 捕获 asyncio.gather 可能遇到的异常（例如任务被取消）
            logger.error(f"An unexpected error occurred during bulk verification task: {result}")
            # 可以选择如何处理这种任务级别的错误，这里我们简单记录
            # 也可以将其计入 invalid_count 或单独记录
        elif result:
             # result 可能是 (key, status, error) 或 Exception
             if not isinstance(result, Exception) and result:
                 key, status, error = result
                 # 失败信息已在 _verify_single_key 中记录到 failed_keys
             elif isinstance(result, Exception):
                 # 记录任务本身的异常，可以关联到一个特定的 key 如果可能的话
                 # 这里简化处理，只记录日志
                 logger.error(f"Task execution error during bulk verification: {result}")

    valid_count = len(successful_keys)
    invalid_count = len(failed_keys)
    logger.info(f"Bulk verification finished. Valid: {valid_count}, Invalid: {invalid_count}")

    # 根据是否有失败的 key 决定最终消息和状态
    if failed_keys:
        message = f"批量验证完成。成功: {valid_count}, 失败: {invalid_count}。"
        # 即使有失败也认为是部分成功，返回 200 OK，让前端处理详细结果
        return JSONResponse({
            "success": True, # 表示请求处理完成，具体结果看内容
            "message": message,
            "successful_keys": successful_keys,
            "failed_keys": failed_keys,
            "valid_count": valid_count, # 保留计数方便前端快速展示
            "invalid_count": invalid_count
        })
    else:
        # 完全成功
        message = f"批量验证成功完成。所有 {valid_count} 个密钥均有效。"
        return JSONResponse({
            "success": True,
            "message": message,
            "successful_keys": successful_keys,
            "failed_keys": {},
            "valid_count": valid_count,
            "invalid_count": 0
        })