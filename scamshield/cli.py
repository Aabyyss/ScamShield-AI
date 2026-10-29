"""Command-line interface — handy for testing the pipeline without the UI.

    python -m scamshield.cli --sample dubai_hotel
    python -m scamshield.cli "paste a message here"
    python -m scamshield.cli --sample task_scam --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from . import engine
from .samples import SAMPLE_BY_KEY, SAMPLES


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252 and crash on curly quotes / em dashes from samples.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="ScamShield AI — offline job scam detector")
    parser.add_argument("text", nargs="?", help="Message text to analyse")
    parser.add_argument("--sample", choices=sorted(SAMPLE_BY_KEY), help="Use a built-in sample")
    parser.add_argument("--file", help="Read the message from a file")
    parser.add_argument("--model", default="", help="Ollama model name")
    parser.add_argument("--no-ai", action="store_true", help="Rules engine only")
    parser.add_argument("--json", action="store_true", help="Emit raw JSON")
    parser.add_argument("--list-samples", action="store_true", help="Show demo samples")
    args = parser.parse_args(argv)

    if args.list_samples:
        for s in SAMPLES:
            print(f"{s.key:14} {s.expected:6} {s.title}")
        return 0

    if args.sample:
        text = SAMPLE_BY_KEY[args.sample].text
    elif args.file:
        text = open(args.file, encoding="utf-8").read()
    elif args.text:
        text = args.text
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        parser.print_help()
        return 2

    model = args.model or engine.pick_model(engine.list_models())
    result = engine.analyze(text, model=model, use_ai=not args.no_ai)

    if args.json:
        print(json.dumps(asdict(result), indent=2, default=str))
        return 0

    if result.error:
        print(f"[engine] {result.error}", file=sys.stderr)
    print(f"\n  {result.risk_level} RISK  |  {result.risk_score}/100  |  {result.verdict}")
    print(f"  {result.headline}\n")
    if result.summary:
        print(f"  {result.summary}\n")
    for flag in result.red_flags:
        print(f"  [x] [{flag.severity}] {flag.title}")
        if flag.evidence:
            print(f'      "{flag.evidence}"')
        if flag.why_it_matters:
            print(f"      {flag.why_it_matters}")
    if result.recommended_actions:
        print("\n  Next steps:")
        for i, action in enumerate(result.recommended_actions, 1):
            print(f"   {i}. {action}")
    print(
        f"\n  engine={result.engine} model={result.model or '-'} "
        f"latency={result.latency_ms}ms rules={len(result.rule_hits)}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
