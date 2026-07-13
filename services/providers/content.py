from typing import Protocol


class ContentModelProvider(Protocol):
    def generate(self, prompt: str) -> dict:
        ...
