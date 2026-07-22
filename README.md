# SummerDay

SummerDay is a local-first French learning application built around one short
reading lesson and a small set of useful vocabulary each day.

## Current status

The current branch contains the first daily-lesson vertical slice:

- SvelteKit frontend with a daily lesson page
- FastAPI backend with `GET /api/lessons/today`
- French Vikidia article retrieval through the MediaWiki API
- Stanza French NLP for tokenization, multi-word tokens, POS, lemmas,
  morphology, and dependency parsing
- Basic A1 article suitability signals
- Local Ollama lesson generation with schema and source-evidence validation
- Immutable lesson audio packages with configurable TTS providers
- Safe `/media/*` delivery, pronunciation review gate, and timezone-aware daily assignment
- Mutable JSON drafts and immutable date-based published lessons
- Model-independent tests using fake providers

Accounts, placement, SQLite, ASR, pronunciation scoring, review scheduling, and
automatic scheduling are not implemented yet.

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

Copy `.env.example` to `.env`; SummerDay loads it automatically. Set `fake` explicitly for
offline development; production generation defaults to requiring a configured
real command provider. Set
`SUMMERDAY_TTS_PROVIDER=command` and `SUMMERDAY_TTS_COMMAND` for a local CLI TTS
engine. The command must include `{speed}` or `{wpm}` so learning and natural
profiles can use different rates; `{output_path}` is optional and is appended
as the final argument when omitted. French text is sent on stdin. For example:

```text
SUMMERDAY_TTS_COMMAND=my-tts --rate {wpm} --output {output_path}
```

### Piper

Piper is installed with the project dependencies. Download a voice and its
matching `.onnx.json` file into
`data/piper/`:

```bash
mkdir -p data/piper
uv run python -m piper.download_voices --data-dir data/piper fr_FR-siwis-medium
```

Configure the default voice with:

```text
SUMMERDAY_TTS_PROVIDER=piper
SUMMERDAY_PIPER_MODEL=data/piper/fr_FR-siwis-medium.onnx
```

Use `fr_FR-tom-medium` as the alternative male voice. Piper converts the
lesson target WPM to its `length_scale`; adjust `SUMMERDAY_PIPER_BASELINE_WPM`
and `SUMMERDAY_PIPER_LENGTH_SCALE` after listening to generated audio.

Generate alphabet pronunciation files locally with
`scripts/split_french_alphabet.py`. The source recording and generated files
live in the ignored `data/` storage.

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

The `/today` page shows a lesson only after a lesson for the current date has been
published. Before that, the API returns `404`.

## Generate and publish a lesson

Generation can be resumed in two stages. Content generation retrieves a random
Vikidia candidate, analyzes it with Stanza, asks Ollama for structured teaching
content, and writes the draft before any TTS work:

```bash
uv run python -m services.pipeline generate-content
uv run python -m services.pipeline generate-audio
```

`generate-audio` reads the existing draft and analysis, retries only missing or
failed assets, and never fetches a new article. `generate` remains a convenience
command that runs both stages for a new date.

Draft and NLP analysis files are written to:

```text
data/drafts/YYYY-MM-DD.json
data/analysis/YYYY-MM-DD.json
```

Review the pronunciation focus, then mark it approved before publishing:

```bash
uv run python -m services.pipeline review
```

Publishing refuses missing/unapproved/hash-invalid audio and refuses to
overwrite an existing lesson version:

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
SUMMERDAY_TIMEZONE=America/Toronto
SUMMERDAY_DATA_DIR=data
SUMMERDAY_MEDIA_DIR=data/media
SUMMERDAY_VIKIDIA_MAX_BATCHES=5
```

`SUMMERDAY_VIKIDIA_MAX_BATCHES` controls how many random Vikidia batches content
generation tries before failing. It must be a positive integer.

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

## Single-machine deployment

Keep `data/` and `data/media/` on persistent storage and back them up together;
the lesson JSON references immutable media files under the media root. Bind
Ollama and TTS to `127.0.0.1`, run the API behind HTTPS, and proxy `/api/` and
`/media/` through the same origin as the built frontend. Example nginx and
systemd templates are under `deploy/`. Check `/api/health` after deployment.

Do not expose the media directory directly as a filesystem alias: the API
validates the path and serves versioned files with immutable cache headers.

### Automatic midnight publishing

The systemd timer follows the server's local timezone, which must match
`SUMMERDAY_TIMEZONE`. Install the API service and publishing templates, then
enable the API, nginx, and timer so the site remains available after reboot:

```bash
sudo install -m 0644 deploy/summerday-api.service.example /etc/systemd/system/summerday-api.service
sudo install -m 0644 deploy/summerday-publish.service.example /etc/systemd/system/summerday-publish.service
sudo install -m 0644 deploy/summerday-publish.timer.example /etc/systemd/system/summerday-publish.timer
sudo systemctl daemon-reload
sudo systemctl enable --now nginx summerday-api.service summerday-publish.timer
```

At 00:00, the timer resumes or runs content generation, audio generation,
approval, and publication for the local date. If any step fails, it stops
without publishing and records the sanitized error in
`data/release-failures/YYYY-MM-DD.json`.

## Repository boundaries

- Implementation code lives in this repository.
- The nested `SummerDay-spec/` checkout contains private `SPEC.md` and `FUTURE.md`
  files and is ignored by this repository.
- Generated lesson data and NLP models live under ignored `data/`.
- No private specification content should be copied into this README.
