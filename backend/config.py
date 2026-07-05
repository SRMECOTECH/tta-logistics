"""Central configuration: paths, defaults, setting keys."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_EXCEL = DATA_DIR / "TTA.xlsx"
DB_PATH = DATA_DIR / "tta.db"
DB_URL = f"sqlite:///{DB_PATH.as_posix()}"

load_dotenv(PROJECT_ROOT / ".env")

SECRET_KEYS = {"azure_api_key", "openai_api_key", "hf_api_key", "glm_api_key", "api_key"}

# Settings seeded into the DB on first run (env values win where present).
DEFAULT_SETTINGS = {
    # --- AI providers ---
    "ai_provider": os.getenv("AI_PROVIDER", "disabled"),  # disabled | azure_openai | openai | huggingface
    "azure_api_key": os.getenv("AZURE_OPENAI_API_KEY", ""),
    "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", "https://payer.openai.azure.com/"),
    "azure_chat_deployment": os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "gpt-4.1"),
    "azure_api_version": os.getenv("AZURE_OPENAI_VERSION", "2024-12-01-preview"),
    "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
    "openai_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    "hf_api_key": os.getenv("HF_API_KEY", ""),
    "hf_model": os.getenv("HF_MODEL", "Qwen/Qwen2.5-7B-Instruct"),
    # GLM / Zhipu AI — OpenAI-compatible. Flash models (glm-4.5-flash,
    # glm-4.7-flash) are free; glm-4.6 / glm-5.2 are paid but cheap.
    "glm_api_key": os.getenv("GLM_API_KEY", ""),
    "glm_model": os.getenv("GLM_MODEL", "glm-4.5-flash"),
    "glm_base_url": os.getenv("GLM_BASE_URL", "https://api.z.ai/api/paas/v4/"),
    "ai_temperature": "0.3",
    "ai_max_tokens": "900",
    # --- analytics thresholds (configurable in UI) ---
    "otd_target_pct": "95",
    "outlier_z": "3.0",
    "top_n": "10",
    "speed_cap_kmph": "110",
    # --- data ---
    "excel_path": str(DEFAULT_EXCEL),
    # --- API access (X-API-Key header; auto-generated at startup if empty) ---
    "api_key": os.getenv("TTA_API_KEY", ""),
}
