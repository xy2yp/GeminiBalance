# app/services/chat_service.py

import asyncio
import datetime
import json
import re
import time
from copy import deepcopy
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from app.config.config import settings
from app.core.constants import GEMINI_2_FLASH_EXP_SAFETY_SETTINGS
from app.database.services import (
    add_error_log,
    add_request_log,
)
from app.domain.openai_models import ChatRequest, ImageGenerationRequest
from app.handler.message_converter import OpenAIMessageConverter
from app.handler.response_handler import OpenAIResponseHandler
from app.handler.stream_optimizer import openai_optimizer
from app.log.logger import get_openai_logger
from app.service.client.api_client import GeminiApiClient
from app.service.image.image_create_service import ImageCreateService
from app.service.key.key_manager import KeyManager

logger = get_openai_logger()


def _has_media_parts(contents: List[Dict[str, Any]]) -> bool:
    """判断消息是否包含图片、音频或视频部分 (inline_data)"""
    for content in contents:
        if content and "parts" in content and isinstance(content["parts"], list):
            for part in content["parts"]:
                if isinstance(part, dict) and "inline_data" in part:
                    return True
    return False


def _build_tools(
    request: ChatRequest, messages: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """构建工具"""
    tool = dict()
    model = request.model

    if (
        settings.TOOLS_CODE_EXECUTION_ENABLED
        and not (
            model.endswith("-search")
            or "-thinking" in model
            or model.endswith("-image")
            or model.endswith("-image-generation")
        )
        and not _has_media_parts(messages)  # Use the updated check
    ):
        tool["codeExecution"] = {}
        logger.debug("Code execution tool enabled.")
    elif _has_media_parts(messages):
        logger.debug("Code execution tool disabled due to media parts presence.")

    if model.endswith("-search"):
        tool["googleSearch"] = {}

    # 将 request 中的 tools 合并到 tools 中
    if request.tools:
        function_declarations = []
        for item in request.tools:
            if not item or not isinstance(item, dict):
                continue

            if item.get("type", "") == "function" and item.get("function"):
                function = deepcopy(item.get("function"))
                parameters = function.get("parameters", {})
                if parameters.get("type") == "object" and not parameters.get(
                    "properties", {}
                ):
                    function.pop("parameters", None)

                function_declarations.append(function)

        if function_declarations:
            # 按照 function 的 name 去重
            names, functions = set(), []
            for fc in function_declarations:
                if fc.get("name") not in names:
                    names.add(fc.get("name"))
                    functions.append(fc)

            tool["functionDeclarations"] = functions

    # 解决 "Tool use with function calling is unsupported" 问题
    if tool.get("functionDeclarations"):
        tool.pop("googleSearch", None)
        tool.pop("codeExecution", None)

    return [tool] if tool else []


def _get_safety_settings(model: str) -> List[Dict[str, str]]:
    """获取安全设置"""
    # if (
    #     "2.0" in model
    #     and "gemini-2.0-flash-thinking-exp" not in model
    #     and "gemini-2.0-pro-exp" not in model
    # ):
    if model == "gemini-2.0-flash-exp":
        return GEMINI_2_FLASH_EXP_SAFETY_SETTINGS
    return settings.SAFETY_SETTINGS


def _build_payload(
    request: ChatRequest,
    messages: List[Dict[str, Any]],
    instruction: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构建请求payload"""
    payload = {
        "contents": messages,
        "generationConfig": {
            "temperature": request.temperature,
            "stopSequences": request.stop,
            "topP": request.top_p,
            "topK": request.top_k,
        },
        "tools": _build_tools(request, messages),
        "safetySettings": _get_safety_settings(request.model),
    }
    if request.max_tokens is not None:
        payload["generationConfig"]["maxOutputTokens"] = request.max_tokens
    if request.model.endswith("-image") or request.model.endswith("-image-generation"):
        payload["generationConfig"]["responseModalities"] = ["Text", "Image"]
    if request.model.endswith("-non-thinking"):
        payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
    if request.model in settings.THINKING_BUDGET_MAP:
        payload["generationConfig"]["thinkingConfig"] = {
            "thinkingBudget": settings.THINKING_BUDGET_MAP.get(request.model, 1000)
        }

    if (
        instruction
        and isinstance(instruction, dict)
        and instruction.get("role") == "system"
        and instruction.get("parts")
        and not request.model.endswith("-image")
        and not request.model.endswith("-image-generation")
    ):
        payload["systemInstruction"] = instruction

    return payload


class OpenAIChatService:
    """聊天服务"""

    def __init__(self, base_url: str, key_manager: KeyManager = None):
        self.message_converter = OpenAIMessageConverter()
        self.response_handler = OpenAIResponseHandler(config=None)
        self.api_client = GeminiApiClient(base_url, settings.TIME_OUT)
        self.key_manager = key_manager
        self.image_create_service = ImageCreateService()

    def _extract_text_from_openai_chunk(self, chunk: Dict[str, Any]) -> str:
        """从OpenAI响应块中提取文本内容"""
        if not chunk.get("choices"):
            return ""

        choice = chunk["choices"][0]
        if "delta" in choice and "content" in choice["delta"]:
            return choice["delta"]["content"]
        return ""

    def _create_char_openai_chunk(
        self, original_chunk: Dict[str, Any], text: str
    ) -> Dict[str, Any]:
        """创建包含指定文本的OpenAI响应块"""
        chunk_copy = json.loads(json.dumps(original_chunk))  # 深拷贝
        if chunk_copy.get("choices") and "delta" in chunk_copy["choices"][0]:
            chunk_copy["choices"][0]["delta"]["content"] = text
        return chunk_copy

    async def create_chat_completion(
        self,
        request: ChatRequest,
        api_key: str,
    ) -> Union[Dict[str, Any], AsyncGenerator[str, None]]:
        """创建聊天完成"""
        # 转换消息格式
        messages, instruction = self.message_converter.convert(request.messages)

        # 构建请求payload
        payload = _build_payload(request, messages, instruction)

        if request.stream:
            return self._handle_stream_completion(request.model, payload, api_key)
        return await self._handle_normal_completion(request.model, payload, api_key)

    async def _handle_normal_completion(
        self, model: str, payload: Dict[str, Any], api_key: str
    ) -> Dict[str, Any]:
        """处理普通聊天完成"""
        start_time = time.perf_counter()
        request_datetime = datetime.datetime.now()
        is_success = False
        status_code = None
        response = None
        try:
            response = await self.api_client.generate_content(payload, model, api_key)
            usage_metadata = response.get("usageMetadata", {})
            is_success = True
            status_code = 200
            return self.response_handler.handle_response(
                response,
                model,
                stream=False,
                finish_reason="stop",
                usage_metadata=usage_metadata,
            )
        except Exception as e:
            is_success = False
            error_log_msg = str(e)
            logger.error(f"Normal API call failed with error: {error_log_msg}")
            # Try to parse status code from exception
            match = re.search(r"status code (\d+)", error_log_msg)
            if match:
                status_code = int(match.group(1))
            else:
                status_code = 500

            await add_error_log(
                gemini_key=api_key,
                model_name=model,
                error_type="openai-chat-non-stream",
                error_log=error_log_msg,
                error_code=status_code,
                request_msg=payload,
            )
            raise e
        finally:
            end_time = time.perf_counter()
            latency_ms = int((end_time - start_time) * 1000)
            await add_request_log(
                model_name=model,
                api_key=api_key,
                is_success=is_success,
                status_code=status_code,
                latency_ms=latency_ms,
                request_time=request_datetime,
            )

    async def _fake_stream_logic_impl(
        self, model: str, payload: Dict[str, Any], api_key: str
    ) -> AsyncGenerator[str, None]:
        """处理伪流式 (fake stream) 的核心逻辑"""
        logger.info(
            f"Fake streaming enabled for model: {model}. Calling non-streaming endpoint."
        )
        keep_sending_empty_data = True

        async def send_empty_data_locally() -> AsyncGenerator[str, None]:
            """定期发送空数据以保持连接"""
            while keep_sending_empty_data:
                await asyncio.sleep(settings.FAKE_STREAM_EMPTY_DATA_INTERVAL_SECONDS)
                if keep_sending_empty_data:
                    empty_chunk = {
                        "id": f"chatcmpl-fake-heartbeat-{model}-{time.time()}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(empty_chunk)}\n\\n"
                    logger.debug("Sent empty data chunk for fake stream heartbeat.")

        empty_data_generator = send_empty_data_locally()
        api_response_task = asyncio.create_task(
            self.api_client.generate_content(payload, model, api_key)
        )

        try:
            while not api_response_task.done():
                try:
                    next_empty_chunk = await asyncio.wait_for(
                        empty_data_generator.__anext__(), timeout=0.1
                    )
                    yield next_empty_chunk
                except asyncio.TimeoutError:
                    pass  # Check api_response_task again
                except (
                    StopAsyncIteration
                ):  # Should not happen if keep_sending_empty_data is managed
                    break

            response = await api_response_task  # Get API response or exception
        finally:
            keep_sending_empty_data = False  # Stop sending empty data

        # Helper to create a base chunk for various scenarios
        def create_base_chunk(role_content=""):
            return {
                "id": f"chatcmpl-fake-response-{model}-{time.time()}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": role_content},
                        "finish_reason": None,
                    }
                ],
            }

        if response and response.get("candidates"):
            candidate = response["candidates"][0]
            if candidate.get("content") and candidate["content"].get("parts"):
                full_text = "".join(
                    part.get("text", "")
                    for part in candidate["content"]["parts"]
                    if part.get("text")
                )
                base_chunk_for_text = create_base_chunk()
                final_chunk = self._create_char_openai_chunk(
                    base_chunk_for_text, full_text
                )
                final_chunk["choices"][0]["finish_reason"] = "stop"
                yield f"data: {json.dumps(final_chunk)}\n\\n"
                logger.info(f"Sent full response content for fake stream: {model}")
            else:
                logger.warning(
                    f"Unexpected response structure (no parts/text) in fake stream for model {model}: {response}"
                )
                base_chunk_for_empty = create_base_chunk()
                empty_final_chunk = self._create_char_openai_chunk(
                    base_chunk_for_empty, ""
                )
                empty_final_chunk["choices"][0]["finish_reason"] = "stop"
                yield f"data: {json.dumps(empty_final_chunk)}\n\\n"
        else:
            error_message = "Failed to get response from model"
            if (
                response and isinstance(response, dict) and response.get("error")
            ):  # Check if response itself is an error structure
                # Safely access nested 'message'
                error_details = response.get("error")
                if isinstance(error_details, dict):
                    error_message = error_details.get("message", error_message)

            logger.error(
                f"No candidates or error in response for fake stream model {model}: {response}"
            )
            base_chunk_for_error = create_base_chunk()
            error_chunk = self._create_char_openai_chunk(
                base_chunk_for_error, json.dumps({"error": error_message})
            )
            error_chunk["choices"][0]["finish_reason"] = "stop"
            yield f"data: {json.dumps(error_chunk)}\n\\n"

    async def _real_stream_logic_impl(
        self, model: str, payload: Dict[str, Any], api_key: str
    ) -> AsyncGenerator[str, None]:
        """处理真实流式 (real stream) 的核心逻辑"""
        tool_call_flag = False
        async for line in self.api_client.stream_generate_content(
            payload, model, api_key
        ):
            if line.startswith("data:"):
                chunk_str = line[6:]
                if not chunk_str or chunk_str.isspace():  # handle empty data part
                    logger.debug(
                        f"Received empty data line for model {model}, skipping."
                    )
                    continue
                try:
                    chunk = json.loads(chunk_str)
                except json.JSONDecodeError:
                    logger.error(
                        f"Failed to decode JSON from stream for model {model}: {chunk_str}"
                    )
                    continue  # Skip malformed chunk

                openai_chunk = self.response_handler.handle_response(
                    chunk, model, stream=True, finish_reason=None
                )
                if openai_chunk:
                    text = self._extract_text_from_openai_chunk(openai_chunk)
                    if text and settings.STREAM_OPTIMIZER_ENABLED:
                        async for (
                            optimized_chunk_data
                        ) in openai_optimizer.optimize_stream_output(
                            text,
                            lambda t: self._create_char_openai_chunk(openai_chunk, t),
                            lambda c: f"data: {json.dumps(c)}\n\\n",
                        ):
                            yield optimized_chunk_data
                    else:
                        # Check for tool_calls more robustly
                        if openai_chunk.get("choices") and openai_chunk["choices"][
                            0
                        ].get("delta", {}).get("tool_calls"):
                            tool_call_flag = True
                        elif openai_chunk.get("choices") and openai_chunk["choices"][
                            0
                        ].get("delta", {}).get(
                            "function_call"
                        ):  # For older compatibility
                            tool_call_flag = True

                        yield f"data: {json.dumps(openai_chunk)}\n\\n"

        if tool_call_flag:
            yield f"data: {json.dumps(self.response_handler.handle_response({}, model, stream=True, finish_reason='tool_calls'))}\n\\n"
        else:
            yield f"data: {json.dumps(self.response_handler.handle_response({}, model, stream=True, finish_reason='stop'))}\n\\n"

    async def _handle_stream_completion(
        self, model: str, payload: Dict[str, Any], api_key: str
    ) -> AsyncGenerator[str, None]:
        """处理流式聊天完成，添加重试逻辑和假流式支持"""
        retries = 0
        max_retries = settings.MAX_RETRIES
        is_success = False
        status_code = None
        final_api_key = api_key  # Initialize with the provided API key

        while retries < max_retries:
            start_time = time.perf_counter()
            request_datetime = datetime.datetime.now()
            current_attempt_key = (
                final_api_key  # Use the potentially updated key for this attempt
            )

            try:
                stream_generator = None
                if settings.FAKE_STREAM_ENABLED:
                    logger.info(
                        f"Using fake stream logic for model: {model}, Attempt: {retries + 1}"
                    )
                    stream_generator = self._fake_stream_logic_impl(
                        model, payload, current_attempt_key
                    )
                else:
                    logger.info(
                        f"Using real stream logic for model: {model}, Attempt: {retries + 1}"
                    )
                    stream_generator = self._real_stream_logic_impl(
                        model, payload, current_attempt_key
                    )

                async for chunk_data in stream_generator:
                    yield chunk_data

                # If the generator completes, it means all its data chunks (including stop/tool_calls) were yielded.
                # Now, we send the [DONE] marker for the stream.
                yield "data: [DONE]\n\\n"
                logger.info(
                    f"Streaming completed successfully for model: {model}, FakeStream: {settings.FAKE_STREAM_ENABLED}, Attempt: {retries + 1}"
                )
                is_success = True
                status_code = 200
                break  # Successful attempt, exit retry loop

            except Exception as e:
                retries += 1
                is_success = False  # Ensure is_success is false for this attempt
                error_log_msg = str(e)
                logger.warning(
                    f"Streaming API call failed with error: {error_log_msg}. Attempt {retries} of {max_retries} with key {current_attempt_key}"
                )

                match = re.search(r"status code (\\d+)", error_log_msg)
                if match:
                    status_code = int(match.group(1))
                else:
                    # Distinguish between client-side (e.g., asyncio.TimeoutError) and potential API errors
                    if isinstance(
                        e, asyncio.TimeoutError
                    ):  # Example, can add more specific client errors
                        status_code = 408  # Request Timeout
                    else:
                        status_code = (
                            500  # Internal Server Error as default for other exceptions
                        )

                await add_error_log(
                    gemini_key=current_attempt_key,
                    model_name=model,
                    error_type="openai-chat-stream",
                    error_log=error_log_msg,
                    error_code=status_code,
                    request_msg=payload,
                )

                if self.key_manager:
                    new_api_key = await self.key_manager.handle_api_failure(
                        current_attempt_key, retries
                    )
                    if new_api_key and new_api_key != current_attempt_key:
                        final_api_key = new_api_key  # Update for the NEXT attempt
                        logger.info(
                            f"Switched to new API key for next attempt: {final_api_key}"
                        )
                    elif not new_api_key:
                        logger.error(
                            f"No valid API key available after {retries} retries, ceasing attempts for this request."
                        )
                        break  # No new key, stop retrying
                    # If new_api_key is the same as current_attempt_key, continue retrying with it if retries < max_retries
                else:
                    logger.error(
                        "KeyManager not available, cannot switch API key. Ceasing attempts for this request."
                    )
                    break  # No KeyManager, stop retrying

                if retries >= max_retries:
                    logger.error(
                        f"Max retries ({max_retries}) reached for streaming model {model}."
                    )
                    # The loop will terminate, and the final error handling outside the loop will take over.
            finally:
                end_time = time.perf_counter()
                latency_ms = int((end_time - start_time) * 1000)
                # Log with the key used for THIS specific attempt
                await add_request_log(
                    model_name=model,
                    api_key=current_attempt_key,
                    is_success=is_success,  # This reflects the success of the current attempt
                    status_code=status_code,
                    latency_ms=latency_ms,
                    request_time=request_datetime,
                )

        # After the loop, if not successful, yield a final error message and [DONE]
        if (
            not is_success
        ):  # This 'is_success' is the overall success status after all retries
            logger.error(
                f"Streaming failed permanently for model {model} after {retries} attempts."
            )
            yield f"data: {json.dumps({'error': f'Streaming failed after {retries} retries.'})}\n\\n"
            yield "data: [DONE]\n\\n"

    async def create_image_chat_completion(
        self, request: ChatRequest, api_key: str
    ) -> Union[Dict[str, Any], AsyncGenerator[str, None]]:

        image_generate_request = ImageGenerationRequest()
        image_generate_request.prompt = request.messages[-1]["content"]
        image_res = self.image_create_service.generate_images_chat(
            image_generate_request
        )

        if request.stream:
            return self._handle_stream_image_completion(
                request.model, image_res, api_key
            )
        else:
            return await self._handle_normal_image_completion(
                request.model, image_res, api_key
            )

    async def _handle_stream_image_completion(
        self, model: str, image_data: str, api_key: str
    ) -> AsyncGenerator[str, None]:
        logger.info(f"Starting stream image completion for model: {model}")
        start_time = time.perf_counter()
        request_datetime = datetime.datetime.now()
        is_success = False
        status_code = None

        try:
            if image_data:
                openai_chunk = self.response_handler.handle_image_chat_response(
                    image_data, model, stream=True, finish_reason=None
                )
                if openai_chunk:
                    # 提取文本内容
                    text = self._extract_text_from_openai_chunk(openai_chunk)
                    if text:
                        # 使用流式输出优化器处理文本输出
                        async for (
                            optimized_chunk
                        ) in openai_optimizer.optimize_stream_output(
                            text,
                            lambda t: self._create_char_openai_chunk(openai_chunk, t),
                            lambda c: f"data: {json.dumps(c)}\n\n",
                        ):
                            yield optimized_chunk
                    else:
                        # 如果没有文本内容（如图片URL等），整块输出
                        yield f"data: {json.dumps(openai_chunk)}\n\n"
            yield f"data: {json.dumps(self.response_handler.handle_response({}, model, stream=True, finish_reason='stop'))}\n\n"
            logger.info(
                f"Stream image completion finished successfully for model: {model}"
            )
            is_success = True
            status_code = 200
            yield "data: [DONE]\n\n"
        except Exception as e:
            is_success = False
            error_log_msg = f"Stream image completion failed for model {model}: {e}"
            logger.error(error_log_msg)
            status_code = 500
            await add_error_log(
                gemini_key=api_key,
                model_name=model,
                error_type="openai-image-stream",
                error_log=error_log_msg,
                error_code=status_code,
                request_msg={"image_data_truncated": image_data[:1000]},
            )
            yield f"data: {json.dumps({'error': error_log_msg})}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            end_time = time.perf_counter()
            latency_ms = int((end_time - start_time) * 1000)
            logger.info(
                f"Stream image completion for model {model} took {latency_ms} ms. Success: {is_success}"
            )
            await add_request_log(
                model_name=model,
                api_key=api_key,
                is_success=is_success,
                status_code=status_code,
                latency_ms=latency_ms,
                request_time=request_datetime,
            )

    async def _handle_normal_image_completion(
        self, model: str, image_data: str, api_key: str
    ) -> Dict[str, Any]:
        logger.info(f"Starting normal image completion for model: {model}")
        start_time = time.perf_counter()
        request_datetime = datetime.datetime.now()
        is_success = False
        status_code = None
        result = None

        try:
            result = self.response_handler.handle_image_chat_response(
                image_data, model, stream=False, finish_reason="stop"
            )
            logger.info(
                f"Normal image completion finished successfully for model: {model}"
            )
            is_success = True
            status_code = 200
            return result
        except Exception as e:
            is_success = False
            error_log_msg = f"Normal image completion failed for model {model}: {e}"
            logger.error(error_log_msg)
            status_code = 500
            await add_error_log(
                gemini_key=api_key,
                model_name=model,
                error_type="openai-image-non-stream",
                error_log=error_log_msg,
                error_code=status_code,
                request_msg={"image_data_truncated": image_data[:1000]},
            )
            # Re-raise the exception so the caller knows about the failure
            raise e
        finally:
            end_time = time.perf_counter()
            latency_ms = int((end_time - start_time) * 1000)
            logger.info(
                f"Normal image completion for model {model} took {latency_ms} ms. Success: {is_success}"
            )
            await add_request_log(
                model_name=model,
                api_key=api_key,
                is_success=is_success,
                status_code=status_code,
                latency_ms=latency_ms,
                request_time=request_datetime,
            )
