from contextlib import asynccontextmanager
from pathlib import Path # Add pathlib import
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config.config import settings, sync_initial_settings
from app.log.logger import get_application_logger
from app.middleware.middleware import setup_middlewares
from app.exception.exceptions import setup_exception_handlers
from app.router.routes import setup_routers
from app.service.key.key_manager import get_key_manager_instance
from app.database.connection import connect_to_db, disconnect_from_db
from app.database.initialization import initialize_database
from app.scheduler.key_checker import start_scheduler, stop_scheduler
from app.service.update.update_service import check_for_updates

logger = get_application_logger()

# Define project paths using pathlib
# Assuming this file is at app/core/application.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VERSION_FILE_PATH = PROJECT_ROOT / "VERSION"
STATIC_DIR = PROJECT_ROOT / "app" / "static"
TEMPLATES_DIR = PROJECT_ROOT / "app" / "templates"


def _get_current_version(default_version: str = "0.0.0") -> str:
    """Reads the current version from the VERSION file."""
    version_file = VERSION_FILE_PATH # Use Path object
    try:
        # Use Path object's open method
        with version_file.open('r', encoding='utf-8') as f:
            version = f.read().strip()
        if not version:
            logger.warning(f"VERSION file ('{version_file}') is empty. Using default version '{default_version}'.")
            return default_version
        return version
    except FileNotFoundError:
        logger.warning(f"VERSION file not found at '{version_file}'. Using default version '{default_version}'.")
        return default_version
    except IOError as e:
        logger.error(f"Error reading VERSION file ('{version_file}'): {e}. Using default version '{default_version}'.")
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


# --- Helper functions for lifespan ---

async def _setup_database_and_config(app_settings):
    """Initializes database, syncs settings, and initializes KeyManager."""
    initialize_database()
    logger.info("Database initialized successfully")
    await connect_to_db()
    await sync_initial_settings()
    # Initialize KeyManager using potentially updated settings
    await get_key_manager_instance(app_settings.API_KEYS)
    logger.info("Database, config sync, and KeyManager initialized successfully")

async def _shutdown_database():
    """Disconnects from the database."""
    await disconnect_from_db()
    logger.info("Disconnected from database.")

def _start_scheduler():
    """Starts the background scheduler."""
    try:
        start_scheduler()
        logger.info("Scheduler started successfully.")
    except Exception as e:
         logger.error(f"Failed to start scheduler: {e}")

def _stop_scheduler():
    """Stops the background scheduler."""
    stop_scheduler()
    logger.info("Scheduler stopped.")

async def _perform_update_check(app: FastAPI):
    """Checks for updates and stores the info in app.state."""
    update_available, latest_version, error_message = await check_for_updates()
    current_version = _get_current_version() # Read from VERSION file
    update_info = {
        "update_available": update_available,
        "latest_version": latest_version,
        "error_message": error_message,
        "current_version": current_version
    }
    # Ensure app.state exists and store update info
    if not hasattr(app, "state"):
        from starlette.datastructures import State
        app.state = State()
    app.state.update_info = update_info
    logger.info(f"Update check completed. Info: {update_info}")

# --- Application Lifespan ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the application startup and shutdown events.
    
    Args:
        app: FastAPI应用实例
    """
    # Startup events
    logger.info("Application starting up...")
    try:
        # Setup database, config, and KeyManager
        await _setup_database_and_config(settings) # Pass settings object

        # Perform update check after core components are ready
        await _perform_update_check(app)

        # Start the scheduler
        _start_scheduler()

    except Exception as e:
        logger.critical(f"Critical error during application startup: {str(e)}", exc_info=True)
        # Depending on the severity, you might want to prevent the app from fully starting
        # For now, we log critically and let it yield, potentially in a broken state.
        # Consider adding more robust error handling here if startup failures should halt the app.

    yield  # Application runs

    # Shutdown events
    logger.info("Application shutting down...")
    _stop_scheduler()
    await _shutdown_database()

def create_app() -> FastAPI:
    """
    创建并配置FastAPI应用程序实例
    
    Returns:
        FastAPI: 配置好的FastAPI应用程序实例
    """
    # Removed: initialize_app() call

    # 创建FastAPI应用
    # Read version from file for consistency
    current_version = _get_current_version()
    app = FastAPI(
        title="Gemini Balance API",
        description="Gemini API代理服务，支持负载均衡和密钥管理",
        version=current_version,
        lifespan=lifespan
    )

    # Initialize app.state early to ensure it exists before lifespan potentially uses it
    if not hasattr(app, "state"):
        from starlette.datastructures import State
        app.state = State()
    # Set a default/initial state for update_info
    app.state.update_info = {
        "update_available": False,
        "latest_version": None,
        "error_message": "Initializing...",
        "current_version": current_version # Use version read earlier
    }

    # 配置静态文件
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # 配置中间件
    setup_middlewares(app)
    
    # 配置异常处理器
    setup_exception_handlers(app)
    
    # 配置路由
    setup_routers(app)
    
    return app
