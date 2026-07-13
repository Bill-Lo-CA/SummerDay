# TTS evaluation

The harness compares the same French cases at learning and natural speed. It
does not put generated audio in Git.

Use the fake provider for CI smoke tests:

```bash
uv run python -m scripts.evaluate_tts --output /tmp/someaday-tts-eval
```

For a local CLI provider, the command receives text on stdin and the output
path as its final argument:

```bash
uv run python -m scripts.evaluate_tts \
  --provider command \
  --command 'piper --model fr_FR-upmc-medium.onnx --output_file' \
  --model fr_FR-upmc-medium \
  --output /tmp/someaday-tts-eval
```

The summary records latency and output size. Human review must still assess
French pronunciation, letter names, lexical units, connected speech, rate,
resource use, stability, and licensing before selecting a default provider.
