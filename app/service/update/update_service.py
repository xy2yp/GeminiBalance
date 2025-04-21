import httpx
from packaging import version
from typing import Optional, Tuple

from app.config.config import settings
from app.log.logger import get_update_logger

logger = get_update_logger()

# GitHub repository details are read from settings (defined in app/config/config.py or environment variables)

# GITHUB_API_URL will be constructed inside the function to ensure settings are loaded

VERSION_FILE_PATH = "VERSION" # Path relative to project root

async def check_for_updates() -> Tuple[bool, Optional[str], Optional[str]]:
    """
    通过比较当前版本与最新的 GitHub release 来检查应用程序更新。

    Returns:
        Tuple[bool, Optional[str], Optional[str]]: 一个元组，包含：
            - bool: 如果有可用更新则为 True，否则为 False。
            - Optional[str]: 如果有可用更新，则为最新的版本字符串，否则为 None。
            - Optional[str]: 如果检查失败，则为错误消息，否则为 None。
    """
    try:
        # Read current version from VERSION file
        # Ensure the path is correct relative to the execution context or use absolute path if needed
        # Assuming execution from project root d:/develop/pythonProjects/gemini-balance
        with open(VERSION_FILE_PATH, 'r', encoding='utf-8') as f:
            current_v = f.read().strip()
        if not current_v:
            logger.error(f"VERSION file ('{VERSION_FILE_PATH}') is empty.")
            return False, None, f"VERSION file ('{VERSION_FILE_PATH}') is empty."
    except FileNotFoundError:
        logger.error(f"VERSION file not found at '{VERSION_FILE_PATH}'. Make sure it exists in the project root.")
        return False, None, f"VERSION file not found at '{VERSION_FILE_PATH}'."
    except IOError as e:
        logger.error(f"Error reading VERSION file ('{VERSION_FILE_PATH}'): {e}")
        return False, None, f"Error reading VERSION file ('{VERSION_FILE_PATH}')."

    logger.info(f"当前应用程序版本 (from {VERSION_FILE_PATH}): {current_v}")

    # Check if repository details are configured in settings
    if not settings.GITHUB_REPO_OWNER or not settings.GITHUB_REPO_NAME or \
       settings.GITHUB_REPO_OWNER == "your_owner" or settings.GITHUB_REPO_NAME == "your_repo":
        logger.warning("GitHub repository owner/name not configured in settings. Skipping update check.")
        return False, None, "Update check skipped: Repository not configured in settings."

    # Construct the API URL inside the function to ensure settings are loaded
    github_api_url = f"https://api.github.com/repos/{settings.GITHUB_REPO_OWNER}/{settings.GITHUB_REPO_NAME}/releases/latest"
    logger.debug(f"Checking for updates at URL: {github_api_url}") # Log the URL for debugging

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 添加 User-Agent 头，GitHub API 可能需要
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": f"{settings.GITHUB_REPO_NAME}-UpdateChecker/1.0" # Use repo name from settings for User-Agent
            }
            response = await client.get(github_api_url, headers=headers) # Use the locally constructed URL
            response.raise_for_status() # 对错误的 HTTP 状态码（4xx 或 5xx）抛出异常

            latest_release = response.json()
            latest_v_str = latest_release.get("tag_name")

            if not latest_v_str:
                logger.warning("在最新的 GitHub release 响应中找不到 'tag_name'。")
                return False, None, "无法从 GitHub 解析最新版本。"

            # 移除 tag 名称中可能存在的 'v' 前缀
            if latest_v_str.startswith('v'):
                latest_v_str = latest_v_str[1:]

            logger.info(f"在 GitHub 上找到的最新版本: {latest_v_str}")

            # 比较版本
            current_version = version.parse(current_v)
            latest_version = version.parse(latest_v_str)

            if latest_version > current_version:
                logger.info(f"有可用更新: {current_v} -> {latest_v_str}")
                return True, latest_v_str, None
            else:
                logger.info("应用程序已是最新版本。")
                return False, None, None

    except httpx.HTTPStatusError as e:
        logger.error(f"检查更新时发生 HTTP 错误: {e.response.status_code} - {e.response.text}")
        # 避免向用户显示详细的错误文本
        error_msg = f"获取更新信息失败 (HTTP {e.response.status_code})。"
        if e.response.status_code == 404:
            error_msg += " 请检查仓库名称是否正确或仓库是否有发布版本。"
        elif e.response.status_code == 403:
             error_msg += " API 速率限制或权限问题。"
        return False, None, error_msg
    except httpx.RequestError as e:
        logger.error(f"检查更新时发生网络错误: {e}")
        return False, None, "更新检查期间发生网络错误。"
    except version.InvalidVersion:
        # Note: latest_v_str might not be defined if the error occurs before fetching it.
        # Consider adding a check or default value for logging.
        latest_v_str_for_log = latest_v_str if 'latest_v_str' in locals() else 'N/A'
        logger.error(f"发现无效的版本格式。当前 (from {VERSION_FILE_PATH}): '{current_v}', 最新: '{latest_v_str_for_log}'")
        return False, None, "遇到无效的版本格式。"
    except Exception as e:
        logger.error(f"更新检查期间发生意外错误: {e}", exc_info=True)
        return False, None, "发生意外错误。"