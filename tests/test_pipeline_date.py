import sys
from datetime import date
from pathlib import Path

import services.pipeline as pipeline


def test_cli_defaults_to_application_date(monkeypatch, capsys) -> None:
    expected = date(2026, 7, 12)
    captured: dict[str, date] = {}
    monkeypatch.setattr(pipeline, "application_date", lambda: expected)
    def fake_publish(lesson_date: date) -> Path:
        captured["date"] = lesson_date
        return Path("draft.json")

    monkeypatch.setattr(pipeline, "publish", fake_publish)
    monkeypatch.setattr(sys, "argv", ["pipeline", "publish"])

    pipeline.main()

    assert captured["date"] == expected
    assert capsys.readouterr().out == "draft.json\n"
