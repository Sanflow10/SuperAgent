import uuid

import pytest

import core.memory as mem_module
from core.config import Config


@pytest.fixture(autouse=True)
def isolate_memory(tmp_path, monkeypatch):
    """Every test gets its own SQLite DB under tmp_path."""
    db = tmp_path / "test.db"
    monkeypatch.setattr(mem_module, "MEMORY_DB", db)
    yield db


@pytest.fixture
def config():
    return Config()


@pytest.fixture
def run_id():
    return f"test-{uuid.uuid4()}"
