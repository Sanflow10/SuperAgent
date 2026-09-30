import logging
import time

import requests
from requests.exceptions import RequestException

from core.config import Config
from core.util import clean_llm_text


router_logger = logging.getLogger("superagent.router")


class OllamaClient:

    def __init__(self, config: Config):
        self.config = config

        self.url = config.env_str(
            "OLLAMA_URL", "ollama", "url", default="http://127.0.0.1:11434"
        ).rstrip("/")

        self.timeout = config.env_int("LLM_TIMEOUT", "ollama", "timeout", default=300)
        self.retries = max(1, config.env_int("LLM_RETRIES", "ollama", "retries", default=3))

    def ask(self, model: str, system: str, prompt: str, temperature: float = 0.2) -> str:
        last_error = None

        for attempt in range(self.retries):
            try:
                response = requests.post(
                    f"{self.url}/api/chat",
                    json={
                        "model": model,
                        "stream": False,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        "options": {
                            "temperature": temperature,
                            "stop": ["</tool>", "</" + "parameter>"],
                        },
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()

                data = response.json()
                content = (data.get("message") or {}).get("content", "")

                if not content:
                    raise RuntimeError("Ollama retornou conteúdo vazio.")

                return clean_llm_text(content)

            except (RequestException, ValueError, RuntimeError) as exc:
                last_error = exc
                if attempt < self.retries - 1:
                    time.sleep(2 ** attempt)

        raise RuntimeError(
            f"Ollama indisponível após {self.retries} tentativas: {last_error}"
        )


class ModelRouter:

    def __init__(self, config: Config):
        self.config = config
        self.client = OllamaClient(config)

    def ask(self, role: str, system: str, prompt: str) -> str:
        model = self.config.model(role)
        temperature = self.config.temperature(role)

        started = time.monotonic()
        try:
            return self.client.ask(
                model=model, system=system, prompt=prompt, temperature=temperature
            )
        finally:
            router_logger.info(
                "model_call",
                extra={
                    "event": "model_call",
                    "role": role,
                    "model": model,
                    "elapsed_s": round(time.monotonic() - started, 2),
                },
            )
