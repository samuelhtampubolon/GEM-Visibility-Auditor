import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

KEY_VARS = ["ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY",
            "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "MISTRAL_API_KEY"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """Tiap tes mulai tanpa kunci API dan tanpa .env dari folder kerja."""
    for k in KEY_VARS:
        monkeypatch.delenv(k, raising=False)
    for k in list(os.environ):
        if k.startswith("GEM_") and k.endswith("_BASE_URL"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEM_RETRY_BASE", "0.01")
    monkeypatch.chdir(tmp_path)
    yield


@pytest.fixture()
def mock_server():
    from mock_llm_server import start_server
    srv = start_server()
    yield srv
    srv.shutdown()


@pytest.fixture(scope="session")
def root():
    return ROOT
