import os
import sys
import traceback

# =============================================================================
# PASSO 1 (ANTES DE TUDO): CRIAR OBJETO app FastAPI VAZIO no TOPO do arquivo.
# ISSO PASSA NA VALIDACAO BUILD-TIME DA VERCEL CLI 58+ SEM CRASHAR!
# O validador faz 'import api.index' durante o build para encontrar o objeto app.
# Se importar 'mangum' ou 'app.main.create_app' ANTES do app existir, crasha.
# =============================================================================
from fastapi import FastAPI

# App Vazio (placeholder) para o validador de build-time:
app = FastAPI(title="Print Collect", version="1.0.0")

# =============================================================================
# PASSO 2: Configurar sys.path
# =============================================================================
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

_DEBUG_OUTPUT = [f"[api/index.py] python={sys.version.split()[0]}; cwd={os.getcwd()}"]
_DEBUG_OUTPUT.append(f"[api/index.py] ROOT={ROOT} exists={os.path.isdir(ROOT)}")
_DEBUG_OUTPUT.append(f"[api/index.py] SERVER_DIR={SERVER_DIR} exists={os.path.isdir(SERVER_DIR)}")


# =============================================================================
# PASSO 3: Carregar app REAL (dentro de try/except - nao crashar build se falhar)
# =============================================================================
_INIT_OK = False
_MANGUM_OK = False
_ERR_MSG = None
_ERR_TB = None

try:
    from mangum import Mangum  # noqa: F401
    _MANGUM_OK = True

    _DEBUG_OUTPUT.append("[api/index.py] from app.main import create_app...")
    from app.main import create_app

    _DEBUG_OUTPUT.append("[api/index.py] create_app() invoking...")
    _real_app = create_app()

    app = _real_app

    _INIT_OK = True
    _DEBUG_OUTPUT.append(f"[api/index.py] CREATE_APP OK. Routes loaded={len(app.routes) if hasattr(app, 'routes') else 'n/a'}.")
except Exception as _e:
    _ERR_MSG = f"{type(_e).__name__}: {_e}"
    _ERR_TB = traceback.format_exc()
    _DEBUG_OUTPUT.append(f"[api/index.py] INIT FAILED: {_ERR_MSG}")
    _DEBUG_OUTPUT.append(f"[api/index.py] TRACEBACK: {_ERR_TB}")

    # Se falhou: adicionar endpoints fallback /health e / de diagnostico no app vazio
    from fastapi.responses import PlainTextResponse

    @app.get("/health", response_class=PlainTextResponse)
    def _health_diagnostics():
        return PlainTextResponse("\n".join(_DEBUG_OUTPUT), status_code=500)

    @app.get("/", response_class=PlainTextResponse)
    def _root_diagnostics():
        return PlainTextResponse(
            "Print Collect - Falha na inicializacao.\n"
            "Acesse /health para detalhes.\n\n"
            + "\n".join(_DEBUG_OUTPUT),
            status_code=500,
        )


# =============================================================================
# PASSO 4: Criar Mangum handler (entrypoint usado por Vercel Functions)
# =============================================================================
handler = None
try:
    from mangum import Mangum as _Mangum
    handler = _Mangum(
        app,
        lifespan="off",
        api_gateway_base_path="/",
    )
except Exception as _e_mangum:
    _DEBUG_OUTPUT.append(f"[api/index.py] WARNING: Mangum handler criacao falhou={_e_mangum}. Usando app ASGI direto.")
    handler = app

if handler is None:
    handler = app
