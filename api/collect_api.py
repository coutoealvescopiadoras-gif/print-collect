import os
import sys
import json
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

_DEBUG_OUTPUT = []
_DEBUG_OUTPUT.append(f"[DEBUG] ROOT={ROOT}")
_DEBUG_OUTPUT.append(f"[DEBUG] SERVER_DIR={SERVER_DIR} exists={os.path.isdir(SERVER_DIR)}")
_DEBUG_OUTPUT.append(f"[DEBUG] sys.path prefix={sys.path[:5]}")
_DEBUG_OUTPUT.append(f"[DEBUG] cwd={os.getcwd()}")
_DEBUG_OUTPUT.append(f"[DEBUG] python_version={sys.version}")

def _make_error_app(message: str):
    """Cria uma app minima ASGI que retorna o erro detalhado em /health."""
    from mangum import Mangum
    from fastapi import FastAPI
    from fastapi.responses import PlainTextResponse
    debug_app = FastAPI(title="Debug Runtime PrintCollect")

    @debug_app.get("/health")
    @debug_app.get("/")
    @debug_app.get("/{rest:path}")
    async def show_error(rest: str = ""):
        body = "\n".join(_DEBUG_OUTPUT) + "\n\n" + message
        return PlainTextResponse(body, status_code=500)

    return Mangum(debug_app, lifespan="off", api_gateway_base_path="/")

try:
    _DEBUG_OUTPUT.append("[DEBUG] importing Mangum...")
    from mangum import Mangum  # noqa: F401
    _DEBUG_OUTPUT.append("[DEBUG] importing create_app from app.main...")
    from app.main import create_app
    _DEBUG_OUTPUT.append("[DEBUG] create_app() invoking...")
    app = create_app()
    _DEBUG_OUTPUT.append("[DEBUG] create_app() SUCCESS! routes=" + str(len(app.routes) if hasattr(app, "routes") else "n/a"))
    handler = Mangum(
        app,
        lifespan="off",
        api_gateway_base_path="/",
    )
except Exception as _e:
    _tb = traceback.format_exc()
    _err = f"=== APP FAILED TO INITIALIZE ===\nException: {type(_e).__name__}: {_e}\n\nTraceback:\n{_tb}\n"
    _DEBUG_OUTPUT.append(_err)
    handler = _make_error_app(_err)
