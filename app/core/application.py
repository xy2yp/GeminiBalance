from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config.config import settings, sync_initial_settings
from app.log.logger import get_application_logger
from app.middleware.middleware import setup_middlewares
from app.exception.exceptions import setup_exception_handlers
from app.router.routes import setup_routers
from app.service.key.key_manager import get_key_manager_instance
from app.core.initialization import initialize_app
from app.database.connection import connect_to_db, disconnect_from_db
from app.database.initialization import initialize_database
from app.scheduler.key_checker import start_scheduler, stop_scheduler
from app.service.update.update_service import check_for_updates

logger = get_application_logger()

VERSION_FILE_PATH = "VERSION" # Path relative to project root

def _get_current_version(default_version: str = "0.0.0") -> str:
    """Reads the current version from the VERSION file."""
    try:
        # Assuming execution from project root d:/develop/pythonProjects/gemini-balance
        with open(VERSION_FILE_PATH, 'r', encoding='utf-8') as f:
            version = f.read().strip()
        if not version:
            logger.warning(f"VERSION file ('{VERSION_FILE_PATH}') is empty. Using default version '{default_version}'.")
            return default_version
        return version
    except FileNotFoundError:
        logger.warning(f"VERSION file not found at '{VERSION_FILE_PATH}'. Using default version '{default_version}'.")
        return default_version
    except IOError as e:
        logger.error(f"Error reading VERSION file ('{VERSION_FILE_PATH}'): {e}. Using default version '{default_version}'.")
        return default_version

# 初始化模板引擎，并添加全局变量
templates = Jinja2Templates(directory="app/templates")

# 定义一个函数来更新模板全局变量
def update_template_globals(app: FastAPI, update_info: dict):
    # Jinja2Templates 实例没有直接更新全局变量的方法
    # 我们需要在请求上下文中传递这些变量，或者修改 Jinja 环境
    # 更简单的方法是将其存储在 app.state 中，并在渲染时传递
    app.state.update_info = update_info
    logger.info(f"Update info stored in app.state: {update_info}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用程序生命周期管理器
    
    Args:
        app: FastAPI应用实例
    """
    # 启动事件
    logger.info("Application starting up...")
    try:
        # 初始化数据库
        initialize_database()
        logger.info("Database initialized successfully")
        
        # 连接到数据库
        await connect_to_db()
        
        # 同步初始配置（DB优先，然后同步回DB）
        await sync_initial_settings()

        # 初始化KeyManager (使用可能已从DB更新的settings)
        await get_key_manager_instance(settings.API_KEYS)
        logger.info("KeyManager initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize application: {str(e)}")
        # 不重新抛出，允许应用继续运行，但记录错误
        # raise # 取消注释以在初始化失败时停止应用

    # 检查更新 (在核心初始化之后)
    update_available, latest_version, error_message = await check_for_updates()
    update_info = {
        "update_available": update_available,
        "latest_version": latest_version,
        "error_message": error_message,
        "current_version": _get_current_version() # Read from VERSION file
    }
    # 将更新信息存储在 app.state 中
    app.state.update_info = update_info
    logger.info(f"Update check completed. Info: {update_info}")


    # 启动调度器 (如果初始化成功)
    try:
        start_scheduler()
        logger.info("Scheduler started successfully.")
    except Exception as e:
         logger.error(f"Failed to start scheduler: {e}")


    yield  # 应用程序运行期间
    
    # 关闭事件
    logger.info("Application shutting down...")
    
    # 停止调度器
    stop_scheduler()
    logger.info("Scheduler stopped.")

    # 断开数据库连接
    await disconnect_from_db()

def create_app() -> FastAPI:
    """
    创建并配置FastAPI应用程序实例
    
    Returns:
        FastAPI: 配置好的FastAPI应用程序实例
    """
    # 初始化应用程序
    initialize_app()
    
    # 创建FastAPI应用
    app = FastAPI(
        title="Gemini Balance API",
        description="Gemini API代理服务，支持负载均衡和密钥管理",
        version="1.0.0",
        lifespan=lifespan
    )

    # 初始化 app.state (如果尚未存在)
    if not hasattr(app, "state"):
        from starlette.datastructures import State
        app.state = State()
    # 确保 update_info 即使在 lifespan 之前访问也不会出错
    app.state.update_info = {"update_available": False, "latest_version": None, "error_message": "Checking...", "current_version": _get_current_version()} # Read from VERSION file for initial state


    # 配置静态文件
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    
    # 配置中间件
    setup_middlewares(app)
    
    # 配置异常处理器
    setup_exception_handlers(app)
    
    # 配置路由
    setup_routers(app)
    
    return app
