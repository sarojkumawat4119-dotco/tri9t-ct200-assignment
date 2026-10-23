import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'ct200.db'}")
GENERATIONS_JSON = Path(os.getenv("GENERATIONS_JSON", str(BASE_DIR / "data/generated_cases.json")))
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
