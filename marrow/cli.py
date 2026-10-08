import argparse
import logging
import os
import sys

from .pipeline import run_pipeline


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="marrow",
        description="Turn a long video into captioned vertical clips for YouTube Shorts and Facebook Reels.",
    )
    parser.add_argument("source", help="YouTube URL or path to a local video file")
    parser.add_argument("--output", default="output", help="Output directory (default: output)")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--clips", type=int, default=None, help="Number of clips")
    parser.add_argument("--duration", type=int, default=None, help="Target clip length in seconds (+/- 10)")
    parser.add_argument("--platform", choices=["shorts", "reels", "both"], default="shorts")
    parser.add_argument("--layout", choices=["crop", "blur_fit"], default=None)
    parser.add_argument("--no-llm", action="store_true", help="Skip Ollama; rank by audio/heuristics")
    parser.add_argument("--force", action="store_true", help="Ignore cached transcript and scores")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    os.environ.setdefault("PYTHONUTF8", "1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")

    results = run_pipeline(
        args.source,
        output_dir=args.output,
        config_path=args.config,
        clip_count=args.clips,
        clip_duration=args.duration,
        platform=args.platform,
        layout=args.layout,
        use_llm=False if args.no_llm else None,
        force=args.force,
    )
    print(f"\nDone: {len(results)} clip(s)")
    for r in results:
        print(f"  #{r['rank']} {r['title']}  ({r['duration']:.0f}s, score {r['score']:.2f})")
        for plat, path in r["files"].items():
            print(f"      {plat}: {path}")


if __name__ == "__main__":
    main()
