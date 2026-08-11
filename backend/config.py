import os
from pathlib import Path
from dotenv import load_dotenv

# Load variables from a .env file in the project root, if present.
load_dotenv()

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = BASE_DIR / "uploads"
CHROMA_DIR = DATA_DIR / "chroma"

DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)
CHROMA_DIR.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{DATA_DIR / 'workspace.db'}"

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "mistral")

API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

# Mail sync runs in the background so application startup and page requests are
# never held up by a remote IMAP server. Set EMAIL_AUTO_SYNC=false to disable.
EMAIL_AUTO_SYNC = os.getenv("EMAIL_AUTO_SYNC", "true").strip().lower() in {"1", "true", "yes", "on"}
EMAIL_AUTO_SYNC_INTERVAL_SECONDS = max(60, int(os.getenv("EMAIL_AUTO_SYNC_INTERVAL_SECONDS", "300")))
EMAIL_AUTO_SYNC_MAX_RESULTS = max(1, min(100, int(os.getenv("EMAIL_AUTO_SYNC_MAX_RESULTS", "20"))))

# CORS: comma-separated allow-list in CORS_ORIGINS (e.g.
# "http://localhost:8000,http://127.0.0.1:8000,https://app.example.com").
# When set, credentials are allowed. When unset (default) we fall back to a
# permissive wildcard WITHOUT credentials — the only valid combination for "*",
# and fine for a local single-user tool.
_cors_env = os.getenv("CORS_ORIGINS", "").strip()
if _cors_env:
    CORS_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()]
    CORS_ALLOW_CREDENTIALS = True
else:
    CORS_ORIGINS = ["*"]
    CORS_ALLOW_CREDENTIALS = False
