import os
import sys
import json
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "server")
PYTHON_LIBS_DIR = os.path.join(ROOT, "python_libs")

# 1) Adicionar pasta local de pacotes (instalados via pip install --target python_libs
#    no installCommand do vercel.json, copiados para /var/task/python_libs em runtime)
if os.path.isdir(PYTHON_LIBS_DIR):
    if PYTHON_LIBS_DIR not in sys.path:
        sys.path.insert(0, PYTHON_LIBS_DIR)

# 2) Adicionar server/ no PYTHONPATH para imports do app.* funcionarem
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

_DEBUG_OUTPUT = []
_DEBUG_OUTPUT.append(f"[DEBUG] ROOT={ROOT}")
_DEBUG_OUTPUT.append(f"[DEBUG] SERVER_DIR={SERVER_DIR} exists={os.path.isdir(SERVER_DIR)}")
_DEBUG_OUTPUT.append(f"[DEBUG] PYTHON_LIBS_DIR={PYTHON_LIBS_DIR} exists={os.path.isdir(PYTHON_LIBS_DIR)}")
if os.path.isdir(PYTHON_LIBS_DIR):
    try:
        _pkgs = os.listdir(PYTHON_LIBS_DIR)[:15]
    except Exception:
        _pkgs = []
    _DEBUG_OUTPUT.append(f"[DEBUG] python_libs contents (first 15): {_pkgs}")
_DEBUG_OUTPUT.append(f"[DEBUG] sys.path prefix={sys.path[:7]}")
_DEBUG_OUTPUT.append(f"[DEBUG] cwd={os.getcwd()}")
_DEBUG_OUTPUT.append(f"[DEBUG] python_version={sys.version}")

def _make_error_app(message: str):
    """Cria uma app minima ASGI que retorna o erro detalhado em /health.
    Nao importa Mangum aqui: o handler ASGI minimo eh retornado diretamente.
    """
    import json as _json

    async def app(scope, receive, send):
        body_text = "\n".join(_DEBUG_OUTPUT) + "\n\n" + message
        body_bytes = body_text.encode("utf-8", errors="replace")
        headers = [
            (b"content-type", b"text/plain; charset=utf-8"),
            (b"content-length", str(len(body_bytes)).encode("ascii")),
        ]
        await send(
            {
                "type": "http.response.start",
                "status": 500,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": body_bytes})

    return app


_MANGUM_OK = False
try:
    _DEBUG_OUTPUT.append("[DEBUG] importing Mangum...")
    from mangum import Mangum  # noqa: F401
    _MANGUM_OK = True
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
    _err = (
        f"=== APP FAILED TO INITIALIZE (MANGUM_OK={_MANGUM_OK}) ===\n"
        f"Exception: {type(_e).__name__}: {_e}\n\nTraceback:\n{_tb}\n"
    )
    _DEBUG_OUTPUT.append(_err)
    handler = _make_error_app(_err)
