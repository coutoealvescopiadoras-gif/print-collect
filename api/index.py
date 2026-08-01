import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from mangum import Mangum
from app.main import create_app

app = create_app()

handler = Mangum(
    app,
    lifespan="off",
    api_gateway_base_path="/",
)
