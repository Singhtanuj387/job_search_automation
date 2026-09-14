"""
Configuration and paths for the Phase 2 Web Application.
"""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "data")))
PROFILE_RESUMES_DIR = DATA_DIR / "profile_resumes"
UPLOADS_DIR = Path(os.environ.get("UPLOADS_DIR", str(BASE_DIR / "uploads")))
APP_DB_PATH = DATA_DIR / "app.db"
PHASE1_DB_PATH = DATA_DIR / "jobs.db"
MASTER_KEY_PATH = DATA_DIR / "master.key"

DATA_DIR.mkdir(parents=True, exist_ok=True)
PROFILE_RESUMES_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Master key for Fernet symmetric encryption of API keys & OAuth tokens
def get_master_key() -> bytes:
    env_key = os.environ.get("APP_MASTER_KEY")
    if env_key:
        return env_key.encode("utf-8")
    if MASTER_KEY_PATH.exists():
        return MASTER_KEY_PATH.read_bytes().strip()
    from cryptography.fernet import Fernet
    new_key = Fernet.generate_key()
    MASTER_KEY_PATH.write_bytes(new_key)
    return new_key
