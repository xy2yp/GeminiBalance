"""
配置路由模块
"""
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.core.security import verify_auth_token
from app.log.logger import get_config_routes_logger, Logger
from app.service.config.config_service import ConfigService

router = APIRouter(prefix="/api/config", tags=["config"])

logger = get_config_routes_logger()

@router.get("", response_model=Dict[str, Any])
async def get_config(request: Request):
    auth_token = request.cookies.get("auth_token")
    if not auth_token or not verify_auth_token(auth_token):
        logger.warning("Unauthorized access attempt to config page")
        return RedirectResponse(url="/", status_code=302)
    return await ConfigService.get_config()


@router.put("", response_model=Dict[str, Any])
async def update_config(config_data: Dict[str, Any], request: Request):
    auth_token = request.cookies.get("auth_token")
    if not auth_token or not verify_auth_token(auth_token):
        logger.warning("Unauthorized access attempt to config page")
        return RedirectResponse(url="/", status_code=302)
    try:
        result = await ConfigService.update_config(config_data)
        # 配置更新成功后，立即更新所有 logger 的级别
        Logger.update_log_levels(config_data["LOG_LEVEL"])
        logger.info("Log levels updated after configuration change.")
        return result
    except Exception as e:
        logger.error(f"Error updating config or log levels: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reset", response_model=Dict[str, Any])
async def reset_config(request: Request):
    auth_token = request.cookies.get("auth_token")
    if not auth_token or not verify_auth_token(auth_token):
        logger.warning("Unauthorized access attempt to config page")
        return RedirectResponse(url="/", status_code=302)
    try:
        return await ConfigService.reset_config()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
