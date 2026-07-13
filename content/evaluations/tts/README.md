# TTS evaluation

The harness compares the same French cases at learning and natural speed. It
does not put generated audio in Git.

Use the fake provider for CI smoke tests:

```bash
uv run python -m scripts.evaluate_tts --output /tmp/someaday-tts-eval
```

For a local CLI provider, include `{speed}` or `{wpm}` in the command so the
learning and natural runs use different settings. `{output_path}` is optional;
when absent, the path is appended as the final argument. Text is sent on stdin:

```bash
uv run python -m scripts.evaluate_tts \
  --provider command \
  --command 'my-tts --model fr_FR-upmc-medium --rate {wpm} --output {output_path}' \
  --model fr_FR-upmc-medium \
  --output /tmp/someaday-tts-eval
```

The summary records latency and output size. Human review must still assess
French pronunciation, letter names, lexical units, connected speech, rate,
resource use, stability, and licensing before selecting a default provider.
