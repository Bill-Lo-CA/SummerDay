from services.pipeline import ollama_generate
from services.providers.ollama import OllamaContentProvider


def test_ollama_provider_matches_content_provider_signature(monkeypatch) -> None:
    monkeypatch.setattr(OllamaContentProvider, "generate", lambda self, prompt: {"prompt": prompt})

    assert ollama_generate("hello") == {"prompt": "hello"}
