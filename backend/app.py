import os
import socket
import sys
from pathlib import Path

# 支持 `python backend/app.py` 与 `uvicorn backend.app:app` 两种启动方式
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.env import PROJECT_ROOT, load_env

load_env()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api import router
from backend.infra.database import init_db

FRONTEND_DIR = PROJECT_ROOT / "frontend" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title="生活助手 API")

    @app.on_event("startup")
    async def _startup_init_db():
        init_db()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _no_cache(request, call_next):
        response = await call_next(request)
        path = request.url.path or ""
        if path == "/" or path.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    app.include_router(router)

    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")

    return app


app = create_app()


def _get_lan_ip() -> str:
    """获取当前主机用于局域网访问的 IPv4 地址。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "无法检测"


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    print(f"本机访问：http://localhost:{port}")
    print(f"本机访问：http://127.0.0.1:{port}")
    print(f"局域网访问：http://{_get_lan_ip()}:{port}")
    uvicorn.run(app, host=host, port=port)
