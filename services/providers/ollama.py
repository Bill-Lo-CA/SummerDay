import json
import os
from urllib.request import Request, urlopen

from services.api.schemas import DailyLesson


class OllamaContentProvider:
    def __init__(self, model: str | None = None, base_url: str | None = None, schema: dict | None = None) -> None:
        self.model = model or os.getenv("OLLAMA_CONTENT_MODEL", "qwen3:8b")
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.schema = schema or DailyLesson.model_json_schema()

    def generate(self, prompt: str) -> dict:
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
            headers={"Content-Type": "application/json", "User-Agent": "SomeADay/0.1"},
        )
        with urlopen(request, timeout=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "600"))) as response:
            return json.loads(json.load(response)["message"]["content"])
