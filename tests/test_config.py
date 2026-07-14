import os

from services.config import load_dotenv


def test_load_dotenv_uses_existing_environment(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SUMMERDAY_TEST_FILE=file\nSUMMERDAY_TEST_EXISTING=file\n")
    monkeypatch.delenv("SUMMERDAY_TEST_FILE", raising=False)
    monkeypatch.setenv("SUMMERDAY_TEST_EXISTING", "environment")

    load_dotenv(env_file)

    assert os.environ["SUMMERDAY_TEST_FILE"] == "file"
    assert os.environ["SUMMERDAY_TEST_EXISTING"] == "environment"
