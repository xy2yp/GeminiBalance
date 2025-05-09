import asyncio
from itertools import cycle
from typing import Dict

from app.config.config import settings
from app.log.logger import get_key_manager_logger

logger = get_key_manager_logger()


class KeyManager:
    def __init__(self, api_keys: list):
        self.api_keys = api_keys
        self.key_cycle = cycle(api_keys)
        self.key_cycle_lock = asyncio.Lock()
        self.failure_count_lock = asyncio.Lock()
        self.key_failure_counts: Dict[str, int] = {key: 0 for key in api_keys}
        self.MAX_FAILURES = settings.MAX_FAILURES
        self.paid_key = settings.PAID_KEY

    async def get_paid_key(self) -> str:
        return self.paid_key

    async def get_next_key(self) -> str:
        """获取下一个API key"""
        async with self.key_cycle_lock:
            return next(self.key_cycle)

    async def is_key_valid(self, key: str) -> bool:
        """检查key是否有效"""
        async with self.failure_count_lock:
            return self.key_failure_counts[key] < self.MAX_FAILURES

    async def reset_failure_counts(self):
        """重置所有key的失败计数"""
        async with self.failure_count_lock:
            for key in self.key_failure_counts:
                self.key_failure_counts[key] = 0

    async def reset_key_failure_count(self, key: str) -> bool:
        """重置指定key的失败计数"""
        async with self.failure_count_lock:
            if key in self.key_failure_counts:
                self.key_failure_counts[key] = 0
                logger.info(f"Reset failure count for key: {key}")
                return True
            logger.warning(
                f"Attempt to reset failure count for non-existent key: {key}"
            )
            return False

    async def get_next_working_key(self) -> str:
        """获取下一可用的API key"""
        initial_key = await self.get_next_key()
        current_key = initial_key

        while True:
            if await self.is_key_valid(current_key):
                return current_key

            current_key = await self.get_next_key()
            if current_key == initial_key:
                # await self.reset_failure_counts() 取消重置
                return current_key

    async def handle_api_failure(self, api_key: str, retries: int) -> str:
        """处理API调用失败"""
        async with self.failure_count_lock:
            self.key_failure_counts[api_key] += 1
            if self.key_failure_counts[api_key] >= self.MAX_FAILURES:
                logger.warning(
                    f"API key {api_key} has failed {self.MAX_FAILURES} times"
                )
        if retries < settings.MAX_RETRIES:
            return await self.get_next_working_key()
        else:
            return ""

    def get_fail_count(self, key: str) -> int:
        """获取指定密钥的失败次数"""
        return self.key_failure_counts.get(key, 0)

    async def get_keys_by_status(self) -> dict:
        """获取分类后的API key列表，包括失败次数"""
        valid_keys = {}
        invalid_keys = {}

        async with self.failure_count_lock:
            for key in self.api_keys:
                fail_count = self.key_failure_counts[key]
                if fail_count < self.MAX_FAILURES:
                    valid_keys[key] = fail_count
                else:
                    invalid_keys[key] = fail_count

        return {"valid_keys": valid_keys, "invalid_keys": invalid_keys}

    async def get_first_valid_key(self) -> str:
        """获取第一个有效的API key"""
        async with self.failure_count_lock:
            for key in self.key_failure_counts:
                if self.key_failure_counts[key] < self.MAX_FAILURES:
                    return key
        # 如果所有 key 都无效，或者列表为空，则尝试返回第一个（如果列表不为空）
        # 或者根据具体逻辑处理，这里保持原样，可能在空列表或全无效时需要调整
        if self.api_keys:
            return self.api_keys[0]
        # 如果 api_keys 为空，这里会出问题。实际应用中应有非空保证或更好处理。
        # 为了保持接口一致性，如果列表为空，可能应该抛出异常或返回特定值。
        # 暂且假设 api_keys 不会为空，或者调用者处理后续的空 key 问题。
        # 根据现有代码，如果api_keys为空，self.api_keys[0]会报错。
        # 如果没有有效key且列表不空，返回第一个。若列表为空，这里会出IndexError。
        # 更安全的做法是：
        if not self.api_keys:
            logger.warning("API key list is empty, cannot get first valid key.")
            # Depending on desired behavior, either raise error or return an indicator like "" or None
            # For now, let's allow it to potentially fail if a key is expected by caller
            # but it's better to be explicit. Let's return empty string for consistency with handle_api_failure
            return ""
        return self.api_keys[
            0
        ]  # Fallback to the first key if no key is "valid" but list is not empty


_singleton_instance = None
_singleton_lock = asyncio.Lock()
_preserved_failure_counts: Dict[str, int] | None = None
_preserved_old_api_keys_for_reset: list | None = None
_preserved_next_key_in_cycle: str | None = None


async def get_key_manager_instance(api_keys: list = None) -> KeyManager:
    """
    获取 KeyManager 单例实例。

    如果尚未创建实例，将使用提供的 api_keys 初始化 KeyManager。
    如果已创建实例，则忽略 api_keys 参数，返回现有单例。
    如果在重置后调用，会尝试恢复之前的状态（失败计数、循环位置）。
    """
    global _singleton_instance, _preserved_failure_counts, _preserved_old_api_keys_for_reset, _preserved_next_key_in_cycle

    async with _singleton_lock:
        if _singleton_instance is None:
            if api_keys is None:
                # This case needs careful handling. If it's the very first call, api_keys are required.
                # If it's after a reset and no api_keys are provided, what should happen?
                # The original ValueError was "API keys are required to initialize the KeyManager".
                # Let's assume if api_keys is None here, it's an error unless we are restoring from non-None _preserved_old_api_keys_for_reset.
                # However, the user's request implies new api_keys will be part of the reset flow.
                # For now, stick to a strict requirement for api_keys if _singleton_instance is None.
                raise ValueError(
                    "API keys are required to initialize or re-initialize the KeyManager instance."
                )
            if not api_keys:  # Handle case where api_keys is an empty list
                logger.warning(
                    "Initializing KeyManager with an empty list of API keys."
                )
                # Consider if this should be an error or allowed. Current KeyManager supports it.

            _singleton_instance = KeyManager(api_keys)
            logger.info(
                f"KeyManager instance created/re-created with {len(api_keys)} API keys."
            )

            # 1. 恢复失败计数
            if _preserved_failure_counts:
                # Initialize new instance's failure_counts for all new keys to 0
                current_failure_counts = {
                    key: 0 for key in _singleton_instance.api_keys
                }
                # Inherit counts for keys that exist in both old and new lists
                for key, count in _preserved_failure_counts.items():
                    if key in current_failure_counts:
                        current_failure_counts[key] = count
                _singleton_instance.key_failure_counts = current_failure_counts
                logger.info("Inherited failure counts for applicable keys.")
            _preserved_failure_counts = None  # Clear after use

            # 2. 调整 key_cycle 的起始点
            start_key_for_new_cycle = None
            if (
                _preserved_old_api_keys_for_reset
                and _preserved_next_key_in_cycle
                and _singleton_instance.api_keys  # Ensure new api_keys list is not empty
            ):
                try:
                    # Find the index of the preserved next key in the *old* list
                    start_idx_in_old = _preserved_old_api_keys_for_reset.index(
                        _preserved_next_key_in_cycle
                    )

                    # Iterate through the old key list (circularly) starting from _preserved_next_key_in_cycle
                    # Find the first key that also exists in the new api_keys list
                    for i in range(len(_preserved_old_api_keys_for_reset)):
                        current_old_key_idx = (start_idx_in_old + i) % len(
                            _preserved_old_api_keys_for_reset
                        )
                        key_candidate = _preserved_old_api_keys_for_reset[
                            current_old_key_idx
                        ]
                        if key_candidate in _singleton_instance.api_keys:
                            start_key_for_new_cycle = key_candidate
                            break
                except ValueError:
                    logger.warning(
                        f"Preserved next key '{_preserved_next_key_in_cycle}' not found in preserved old API keys. "
                        "New cycle will start from the beginning of the new list."
                    )
                except Exception as e:
                    logger.error(
                        f"Error determining start key for new cycle from preserved state: {e}. "
                        "New cycle will start from the beginning."
                    )

            if start_key_for_new_cycle and _singleton_instance.api_keys:
                try:
                    # Find the index of the determined start_key in the new api_keys list
                    target_idx = _singleton_instance.api_keys.index(
                        start_key_for_new_cycle
                    )
                    # Advance the new cycle by calling next() target_idx times
                    # This positions the cycle so that the *next* call to next() will yield start_key_for_new_cycle
                    for _ in range(target_idx):
                        next(_singleton_instance.key_cycle)
                    logger.info(
                        f"Key cycle in new instance advanced. Next call to get_next_key() will yield: {start_key_for_new_cycle}"
                    )
                except ValueError:
                    # This should not happen if start_key_for_new_cycle was correctly found in api_keys
                    logger.warning(
                        f"Determined start key '{start_key_for_new_cycle}' not found in new API keys during cycle advancement. "
                        "New cycle will start from the beginning."
                    )
                except (
                    StopIteration
                ):  # Should not happen with cycle unless api_keys is empty, handled by _singleton_instance.api_keys check
                    logger.error(
                        "StopIteration while advancing key cycle, implies empty new API key list previously missed."
                    )
                except Exception as e:
                    logger.error(
                        f"Error advancing new key cycle: {e}. Cycle will start from beginning."
                    )
            else:
                if _singleton_instance.api_keys:
                    logger.info(
                        "New key cycle will start from the beginning of the new API key list (no specific start key determined or needed)."
                    )
                else:
                    logger.info(
                        "New key cycle not applicable as the new API key list is empty."
                    )

            # 清理所有保存的状态
            _preserved_old_api_keys_for_reset = None
            _preserved_next_key_in_cycle = None
            # _preserved_failure_counts already cleared

        return _singleton_instance


async def reset_key_manager_instance():
    """
    重置 KeyManager 单例实例。
    将保存当前实例的状态（失败计数、旧 API keys、下一个 key 提示）
    以供下一次 get_key_manager_instance 调用时恢复。
    """
    global _singleton_instance, _preserved_failure_counts, _preserved_old_api_keys_for_reset, _preserved_next_key_in_cycle
    async with _singleton_lock:
        if _singleton_instance:
            # 1. 保存失败计数
            _preserved_failure_counts = _singleton_instance.key_failure_counts.copy()

            # 2. 保存旧的 API keys 列表
            _preserved_old_api_keys_for_reset = _singleton_instance.api_keys.copy()

            # 3. 保存 key_cycle 的下一个 key 提示
            # This should be the key that get_next_key() would return next.
            try:
                if (
                    _singleton_instance.api_keys
                ):  # Only if there are keys to cycle through
                    # Calling get_next_key() consumes one key and returns it. This is the key
                    # we want the new cycle to effectively start with.
                    _preserved_next_key_in_cycle = (
                        await _singleton_instance.get_next_key()
                    )
                else:
                    _preserved_next_key_in_cycle = None  # No keys, so no next key
            except (
                StopIteration
            ):  # Should be caught by "if _singleton_instance.api_keys"
                logger.warning(
                    "Could not preserve next key hint: key cycle was empty or exhausted in old instance."
                )
                _preserved_next_key_in_cycle = None
            except Exception as e:
                logger.error(f"Error preserving next key hint during reset: {e}")
                _preserved_next_key_in_cycle = None

            _singleton_instance = None
            logger.info(
                "KeyManager instance has been reset. State (failure counts, old keys, next key hint) preserved for next instantiation."
            )
        else:
            logger.info(
                "KeyManager instance was not set (or already reset), no reset action performed."
            )
