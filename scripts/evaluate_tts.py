import argparse
import json
import time
from pathlib import Path

from services.audio.models import SpeechProfile
from services.providers.command_tts import CommandTTSProvider
from services.providers.fake_tts import FakeTTSProvider
from content.evaluations.tts.cases import evaluation_cases


def profile(speed: str) -> SpeechProfile:
    if speed == "natural":
        return SpeechProfile(
            level="A1", learning_target_wpm=105, natural_target_wpm=105,
            pause_style="natural", articulation="natural", connected_speech="natural",
        )
    return SpeechProfile(
        level="A1", learning_target_wpm=85, natural_target_wpm=105,
        pause_style="clear", articulation="clear", connected_speech="light",
    )


def make_provider(args: argparse.Namespace):
    if args.provider == "fake":
        return FakeTTSProvider()
    if not args.command:
        raise SystemExit("--command is required for --provider command")
    return CommandTTSProvider(args.command, model=args.model)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a local TTS provider.")
    parser.add_argument("--provider", choices=("fake", "command"), default="fake")
    parser.add_argument(
        "--command",
        help="CLI template with {speed} or {wpm}; optionally {output_path}; text is sent on stdin",
    )
    parser.add_argument("--model", default="configured")
    parser.add_argument("--speed", choices=("learning", "natural"), action="append", default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    speeds = args.speed or ["learning", "natural"]
    provider = make_provider(args)
    rows = []
    for speed in speeds:
        speech_profile = profile(speed)
        for index, case in enumerate(evaluation_cases()):
            output = args.output / speed / f"{index:03d}.audio"
            started = time.perf_counter()
            result = provider.synthesize(case.text, output, speech_profile)
            rows.append({
                "category": case.category,
                "text": case.text,
                "speed": speed,
                "provider": result.provider,
                "model": result.model,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "bytes": output.stat().st_size,
            })
    summary = {
        "provider": args.provider,
        "model": args.model,
        "case_count": len(rows),
        "results": rows,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(args.output / "summary.json")


if __name__ == "__main__":
    main()
