from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CONFIG_FILE = ROOT / "config" / "config.yaml"

MEMORY_DIR = ROOT / "memory"
MEMORY_DB = MEMORY_DIR / "agent.db"

WORKSPACE = (ROOT / "workspace").resolve()
SANDBOX = (ROOT / "sandbox").resolve()

LOG_DIR = ROOT / "logs"


for directory in (MEMORY_DIR, WORKSPACE, SANDBOX, LOG_DIR):
    directory.mkdir(parents=True, exist_ok=True)
