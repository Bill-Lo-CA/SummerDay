import json
import os
import socket
from urllib.error import URLError
from urllib.request import Request, urlopen

from services.api.schemas import DailyLesson


class OllamaContentProvider:
    def __init__(self, model: str | None = None, base_url: str | None = None, schema: dict | None = None) -> None:
        self.model = model or os.getenv("OLLAMA_CONTENT_MODEL", "qwen3:8b")
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.schema = schema or DailyLesson.model_json_schema()

    def generate(self, prompt: str) -> dict:
        timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "600"))
        request = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(
                {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "format": self.schema,
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0.2},
                }
            ).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "SummerDay/0.1"},
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(json.load(response)["message"]["content"])
        except (TimeoutError, socket.timeout) as exc:
            raise TimeoutError(
                f"Ollama timed out after {timeout:g}s while generating content "
                f"with model {self.model!r} at {self.base_url}. "
                "Increase OLLAMA_TIMEOUT_SECONDS, use a smaller model, or check Ollama GPU/CPU usage."
            ) from exc
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise TimeoutError(
                    f"Ollama timed out after {timeout:g}s while connecting to {self.base_url} "
                    f"with model {self.model!r}."
                ) from exc
            raise
