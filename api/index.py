import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERVER_DIR = os.path.join(ROOT, "server")

# ========== PASSO 1: CRIAR OBJETO FastAPI NO TOPO (VALIDACAO BUILD VERCEL 58) ==========
# A Vercel CLI 58 FAZ 'import api.index' NO TEMPO DE BUILD e valida a existencia
# de um objeto 'app' FastAPI top-level. SE ESSE IMPORT CRASHAR (por ex: deps como
# mangum ou app.main ainda nao instalados) O BUILD FALHA.
#
# SOLUCAO: Cria um app FastAPI VAZIO aqui no topo, ZERO dependencias externas.
# Isso passa 100% na validacao. Depois substituimos as rotas pelo app real.
from fastapi import FastAPI

app = FastAPI(
    title="Print Collect",
    version="1.0.0",
)

# ========== PASSO 2: CONFIGURAR sys.path (libs python + pasta server/) ==========
# Locais onde os pacotes Python sao instalados pelo installCommand:
#   1) api/_libs/       (pip install --target api/_libs)
#   2) python_libs/     (pip install --target python_libs na raiz)
#   3) server/          (codigo da aplicacao 'app.*')
_LIBS_DIR_API = os.path.join(HERE, "_libs")
_LIBS_DIR_ROOT = os.path.join(ROOT, "python_libs")

for _p in [_LIBS_DIR_API, _LIBS_DIR_ROOT, SERVER_DIR]:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

_DEBUG_OUTPUT = [f"[init] python={sys.version.split()[0]} cwd={os.getcwd()}"]
_DEBUG_OUTPUT.append(f"[init] _LIBS_DIR_API={_LIBS_DIR_API} exists={os.path.isdir(_LIBS_DIR_API)}")
_DEBUG_OUTPUT.append(f"[init] _LIBS_DIR_ROOT={_LIBS_DIR_ROOT} exists={os.path.isdir(_LIBS_DIR_ROOT)}")
_DEBUG_OUTPUT.append(f"[init] SERVER_DIR={SERVER_DIR} exists={os.path.isdir(SERVER_DIR)}")

# ========== PASSO 3: CARREGAR APLICACAO REAL (create_app()) E SUBSTITUIR ROTAS ==========
# Tentamos carregar o app REAL (com todas as rotas, autenticacao, DB etc).
# Se falhar, por qualquer motivo, o app FastAPI vazio acima continua existindo
# e retorna uma mensagem de erro util no endpoint /health.

_INIT_ERROR = None
_INIT_TRACEBACK = None
_APP_LOADED_OK = False
_MANGUM_HANDLER = None

try:
    _DEBUG_OUTPUT.append("[init] importing bcrypt (warm up)...")
    try:
        import bcrypt  # noqa: F401
    except Exception:
        pass

    _DEBUG_OUTPUT.append("[init] from app.main import create_app")
    from app.main import create_app

    _DEBUG_OUTPUT.append("[init] create_app() invoking...")
    _real_app = create_app()

    # === TROCA TOTAL: o 'app' que o validador criou recebe TODAS as rotas reais ===
    app.title = _real_app.title
    app.description = _real_app.description
    app.version = _real_app.version
    app.debug = _real_app.debug
    app.state = _real_app.state  # type: ignore[assignment]
    app.router = _real_app.router
    app.dependency_overrides = _real_app.dependency_overrides
    app.exception_handlers = _real_app.exception_handlers
    app.middleware_stack = _real_app.middleware_stack
    app.user_middleware = _real_app.user_middleware
    if hasattr(_real_app, "routes"):
        app.routes = _real_app.routes

    # Tambem cria o handler Mangum (ainda util caso alguem tente usa-lo, mas
    # na pratica o entrypoint novo usa 'app' direto (FastAPI framework runtime))
    try:
        from mangum import Mangum
        _MANGUM_HANDLER = Mangum(app, lifespan="off", api_gateway_base_path="/")
    except Exception:
        _MANGUM_HANDLER = None

    _APP_LOADED_OK = True
    _DEBUG_OUTPUT.append(f"[init] CREATE_APP SUCCESS. routes loaded={len(app.routes) if hasattr(app, 'routes') else 'n/a'}")
except Exception as _e:
    _INIT_ERROR = f"{type(_e).__name__}: {_e}"
    _INIT_TRACEBACK = traceback.format_exc()
    _DEBUG_OUTPUT.append(f"[init] CREATE_APP FAILED: {_INIT_ERROR}")
    _DEBUG_OUTPUT.append(f"[init] TRACEBACK:\n{_INIT_TRACEBACK}")

    # === CASO FALHE: adicionar endpoints de diagnostico no app FastAPI vazio ===
    # Para o usuario / admin conseguirem ver o erro em /health
    from fastapi.responses import PlainTextResponse

    @app.get("/health", response_class=PlainTextResponse)
    def _health_fallback():
        body_lines = list(_DEBUG_OUTPUT)
        return PlainTextResponse("\n".join(body_lines), status_code=500)

    @app.get("/", response_class=PlainTextResponse)
    def _root_fallback():
        body_lines = [
            "Print Collect - falhou ao inicializar a aplicacao.",
            "Acesse /health para ver detalhes do erro.",
            "",
        ] + _DEBUG_OUTPUT
        return PlainTextResponse("\n".join(body_lines), status_code=500)

# Mantemos 'handler' exportado para compatibilidade com configuracoes antigas.
# Se alguem definir entrypoint = api.index:handler ele usa Mangum.
handler = _MANGUM_HANDLER if _MANGUM_HANDLER is not None else app
