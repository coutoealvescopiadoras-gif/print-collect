import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERVER_DIR = os.path.join(ROOT, "server")

# 1) Diretorio de libs Python INSTALADAS DENTRO de api/_libs (pip install -t api/_libs).
#    A Vercel copia SEMPRE tudo o que esta DENTRO da pasta api/ (a pasta da funcao)
#    para o runtime /var/task/api/ , entao esta pasta SEMPRE chega ao runtime.
LIBS_DIR = os.path.join(HERE, "_libs")
if os.path.isdir(LIBS_DIR):
    if LIBS_DIR not in sys.path:
        sys.path.insert(0, LIBS_DIR)

# 2) Pasta python_libs da raiz (fallback)
PYTHON_LIBS_DIR = os.path.join(ROOT, "python_libs")
if os.path.isdir(PYTHON_LIBS_DIR):
    if PYTHON_LIBS_DIR not in sys.path:
        sys.path.insert(0, PYTHON_LIBS_DIR)

# 3) Pasta server/ (para imports app.*)
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

_DEBUG_OUTPUT = []
_DEBUG_OUTPUT.append(f"[DEBUG] HERE={HERE} exists={os.path.isdir(HERE)}")
_DEBUG_OUTPUT.append(f"[DEBUG] ROOT={ROOT} exists={os.path.isdir(ROOT)}")
_DEBUG_OUTPUT.append(f"[DEBUG] SERVER_DIR={SERVER_DIR} exists={os.path.isdir(SERVER_DIR)}")
_DEBUG_OUTPUT.append(f"[DEBUG] LIBS_DIR (api/_libs)={LIBS_DIR} exists={os.path.isdir(LIBS_DIR)}")
if os.path.isdir(LIBS_DIR):
    try:
        _libs = sorted(os.listdir(LIBS_DIR))[:25]
    except Exception as _e:
        _libs = [f"list_error={_e}"]
    _DEBUG_OUTPUT.append(f"[DEBUG] _libs in api/_libs (first 25): {_libs}")
_DEBUG_OUTPUT.append(f"[DEBUG] PYTHON_LIBS_DIR (raiz)={PYTHON_LIBS_DIR} exists={os.path.isdir(PYTHON_LIBS_DIR)}")
_DEBUG_OUTPUT.append(f"[DEBUG] sys.path[0:8]={sys.path[:8]}")
_DEBUG_OUTPUT.append(f"[DEBUG] cwd={os.getcwd()}")
_DEBUG_OUTPUT.append(f"[DEBUG] python={sys.version}")


def _make_error_app(message: str):
    """App ASGI minimo (sem Mangum) que retorna o erro em texto puro."""
    async def app(scope, receive, send):
        body = ("\n".join(_DEBUG_OUTPUT) + "\n\n" + message).encode("utf-8", errors="replace")
        await send({
            "type": "http.response.start",
            "status": 500,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": body})
    return app


_MANGUM_OK = False
_APP_OK = False
try:
    _DEBUG_OUTPUT.append("[DEBUG] from mangum import Mangum")
    from mangum import Mangum
    _MANGUM_OK = True

    _DEBUG_OUTPUT.append("[DEBUG] from app.main import create_app")
    from app.main import create_app

    _DEBUG_OUTPUT.append("[DEBUG] create_app() invoking")
    app = create_app()
    _APP_OK = True
    _n = len(app.routes) if hasattr(app, "routes") else -1
    _DEBUG_OUTPUT.append(f"[DEBUG] create_app() OK, routes={_n}")

    handler = Mangum(
        app,
        lifespan="off",
        api_gateway_base_path="/",
    )
except Exception as _e:
    _tb = traceback.format_exc()
    _err = (
        f"=== INIT FAILED === MANGUM_OK={_MANGUM_OK} APP_OK={_APP_OK}\n"
        f"Exception: {type(_e).__name__}: {_e}\n"
        f"Traceback:\n{_tb}\n"
    )
    _DEBUG_OUTPUT.append(_err)
    handler = _make_error_app(_err)


# Alias obrigatorio para o VALIDADOR da Vercel CLI 58:
#   Ela detecta framework FastAPI automaticamente quando encontra arquivos .py
#   na pasta api/ e EXIGE um objeto top-level chamado 'app' no entrypoint.
#   Nosso runtime REAL exporta 'handler' (Mangum wrapper). Basta criar um alias
#   'app = handler' para a validacao de build passar sem erros. Em runtime,
#   o entrypoint eh 'api.index:handler' (definido no pyproject.toml), entao
#   este alias nunca eh usado em runtime.
app = handler
