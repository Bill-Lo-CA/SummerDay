# SomeADay

SomeADay is a local-first French learning application built around one short
reading lesson and a small set of useful vocabulary each day.

The name is a working name. The project started from **TwelveADay**, became
**SomeADay**, and may later become **Summer Day**. The implementation does not
depend on the current name.

## Current status

The current branch contains the first daily-lesson vertical slice:

- SvelteKit frontend with a daily lesson page
- FastAPI backend with `GET /api/lessons/today`
- French Vikidia article retrieval through the MediaWiki API
- Stanza French NLP for tokenization, multi-word tokens, POS, lemmas,
  morphology, and dependency parsing
- Basic A1 article suitability signals
- Local Ollama lesson generation with schema and source-evidence validation
- Mutable JSON drafts and immutable date-based published lessons
- Model-independent tests using fake providers

Accounts, placement, SQLite, TTS, ASR, review scheduling, and automatic
scheduling are not implemented yet.

## Requirements

- Python 3.12+
- Node.js and pnpm
- Ollama with a content model such as `qwen3:8b`

Install dependencies:

```bash
uv sync
pnpm --dir apps/web install
```

Download the French Stanza models once:

```bash
uv run python -m services.nlp download
```

Models are stored under `data/stanza/`, which is intentionally ignored by Git.

## Run the application

Start the API in one terminal:

```bash
uv run uvicorn services.api.main:app --reload
```

Start the frontend in another:

```bash
pnpm --dir apps/web dev
```

Open <http://localhost:5173>. The API documentation is available at
<http://localhost:8000/docs>.

The page shows a lesson only after a lesson for the current date has been
published. Before that, the API returns `404`.

## Generate and publish a lesson

Generation retrieves a random Vikidia candidate, analyzes it with Stanza, asks
the local Ollama model for structured teaching content, and writes a draft:

```bash
uv run python -m services.pipeline generate
```

Draft and NLP analysis files are written to:

```text
data/drafts/YYYY-MM-DD.json
data/analysis/YYYY-MM-DD.json
```

Review the draft before publishing it. Publishing refuses to overwrite an
existing lesson version:

```bash
uv run python -m services.pipeline publish
```

A date can be supplied explicitly:

```bash
uv run python -m services.pipeline generate --date 2026-07-12
uv run python -m services.pipeline publish --date 2026-07-12
```

Ollama configuration is optional:

```text
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_CONTENT_MODEL=qwen3:8b
OLLAMA_TIMEOUT_SECONDS=600
```

Ollama may use CPU when GPU capacity is unavailable. Stanza uses CPU by default;
set `STANZA_USE_GPU=1` only when that is deliberate.

## Test

The normal test suite does not require Vikidia, Ollama, GPU access, or downloaded
model execution:

```bash
uv run pytest
pnpm --dir apps/web check
pnpm --dir apps/web build
git diff --check
```

The real generation command is model- and network-dependent and should be run
separately from normal CI.

## Repository boundaries

- Implementation code lives in this repository.
- The nested `SomeADay-spec/` checkout contains private `SPEC.md` and `FUTURE.md`
  files and is ignored by this repository.
- Generated lesson data and NLP models live under ignored `data/`.
- No private specification content should be copied into this README.

