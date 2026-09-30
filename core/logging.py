import json
import logging
from logging.handlers import RotatingFileHandler

from core.paths import LOG_DIR


class JsonFormatter(logging.Formatter):

    RESERVED = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "message",
        "asctime", "taskName",
    })

    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in self.RESERVED or key.startswith("_"):
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def setup_logging(run_id: str, level: str = "INFO"):
    root = logging.getLogger("superagent")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.propagate = False

    if not root.handlers:
        formatter = JsonFormatter()

        console = logging.StreamHandler()
        console.setFormatter(formatter)

        file_handler = RotatingFileHandler(
            LOG_DIR / "superagent.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        root.addHandler(console)
        root.addHandler(file_handler)

    logger = logging.getLogger(f"superagent.run.{run_id}")

    logger.info("run_started", extra={"event": "run_started", "run_id": run_id})

    return logger
