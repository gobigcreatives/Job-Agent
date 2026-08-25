"""Command-line entry point.

    jobagent init              scaffold config/profile.yaml, preferences.yaml from the .example files
    jobagent run                run one discovery+application cycle
    jobagent run --dry-run      discovery + scoring only, nothing is applied to
    jobagent report             reprint the most recent run's summary
    jobagent pending             list application questions waiting on you
    jobagent answer ID "text"   answer one, and remember it for future applications
    jobagent schedule            show the cron expression for your configured search frequency
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from jobagent.config import AppConfig, ConfigError, load_config


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def _cmd_init(args: argparse.Namespace) -> int:
    config_dir = Path(args.config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    pairs = [
        ("profile.example.yaml", "profile.yaml"),
        ("preferences.example.yaml", "preferences.yaml"),
        ("resume.example.md", "resume.md"),
    ]
    created = []
    for example_name, target_name in pairs:
        example = config_dir / example_name
        target = config_dir / target_name
        if target.exists():
            print(f"skip  {target} (already exists)")
            continue
        if not example.exists():
            print(f"warn  {example} not found, skipping {target}")
            continue
        shutil.copy(example, target)
        created.append(target)
        print(f"wrote {target}")
    if created:
        print("\nEdit those files with your details, then run: jobagent run --dry-run")
    return 0


def _build_search_provider(config: AppConfig):
    from jobagent.search.cache import CachingSearchProvider, SearchCache
    from jobagent.search.providers import RateLimitedProvider, build_default_provider

    base = RateLimitedProvider(build_default_provider(), min_delay_seconds=config.preferences.search.request_delay_seconds)
    cache = SearchCache(config.data_dir / "search_cache.db")
    return CachingSearchProvider(base, cache, ttl_hours=config.preferences.search.cache_ttl_hours)


def _cmd_run(args: argparse.Namespace) -> int:
    from jobagent.pipeline import run_cycle
    from jobagent.reporting import format_summary
    from jobagent.tracking.store import Store

    config = load_config(args.config_dir, args.data_dir)
    store = Store(config.data_dir / "jobagent.db")

    search_provider = _build_search_provider(config)

    llm = None
    if not args.dry_run:
        from jobagent.generation.llm import LLMClient

        llm = LLMClient()

    summary = run_cycle(
        config,
        search_provider,
        store,
        llm=llm,
        apply_enabled=not args.dry_run,
        headless=not args.headed,
    )
    print(format_summary(summary))
    if args.dry_run:
        print("\n(dry run — nothing was applied to; matches above are previews of what would be auto-applied)")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from jobagent.tracking.store import Store

    config = load_config(args.config_dir, args.data_dir)
    store = Store(config.data_dir / "jobagent.db")
    last = store.last_run_summary()
    if not last:
        print("No runs recorded yet. Run `jobagent run` first.")
        return 1

    print("JOB SEARCH SUMMARY")
    print()
    print(f"Jobs discovered: {last['jobs_discovered']}")
    print(f"Relevant jobs: {last['jobs_relevant']}")
    print(f"Skipped: {last['jobs_skipped']}")
    print(f"Applications submitted: {last['applications_submitted']}")
    print(f"Waiting for input: {last['waiting_for_input']}")
    print(f"Manual verification required: {last['manual_verification_required']}")
    print(f"Failed: {last['failed']}")
    top = [t for t in last.get("top_applications", []) if t.get("match_score") is not None]
    top.sort(key=lambda t: t["match_score"], reverse=True)
    if top:
        print("\nTop applications:\n")
        for i, entry in enumerate(top[:10], start=1):
            print(f"{i}. {entry['company'] or 'Unknown company'}")
            print(f"   {entry['title']}")
            print(f"   Match: {entry['match_score']:.0f}%")
            if i != len(top[:10]):
                print()
    return 0


def _cmd_pending(args: argparse.Namespace) -> int:
    from jobagent.tracking.store import Store

    config = load_config(args.config_dir, args.data_dir)
    store = Store(config.data_dir / "jobagent.db")
    rows = store.list_pending_inputs(resolved=False)
    if not rows:
        print("Nothing waiting on you.")
        return 0
    for row in rows:
        print(f"[{row['id']}] ({row['kind']}) {row['question']}")
        if row["context"]:
            print(f"      {row['context']}")
    print(f"\nAnswer with: jobagent answer <id> \"<your answer>\"")
    return 0


def _cmd_answer(args: argparse.Namespace) -> int:
    from jobagent.tracking.store import Store

    config = load_config(args.config_dir, args.data_dir)
    store = Store(config.data_dir / "jobagent.db")
    pending = store.get_pending_input(args.id)
    if pending is None:
        print(f"No pending input with id {args.id}")
        return 1
    store.resolve_pending_input(args.id, args.answer)
    if pending["kind"] not in ("other", "manual_review_domain", "captcha"):
        store.set_learned_answer(pending["kind"], args.answer)
        print(f"Recorded. Future '{pending['kind']}' questions will be answered with this automatically.")
    else:
        print("Recorded.")
    return 0


def _cmd_schedule(args: argparse.Namespace) -> int:
    from jobagent.scheduling.scheduler import cron_expression, next_run_time

    config = load_config(args.config_dir, args.data_dir)
    schedule = config.preferences.schedule
    print(f"frequency: {schedule.frequency}")
    if schedule.frequency == "manual":
        print("No schedule configured — run `jobagent run` manually, or on your own trigger.")
        return 0
    print(f"cron (UTC): {cron_expression(schedule)}")
    print(f"next run (UTC): {next_run_time(schedule).isoformat()}")
    print("\nPoint your scheduler (cron, systemd timer, CI schedule, etc.) at: jobagent run")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobagent", description="Autonomous job discovery and application agent")
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="scaffold config files from the .example templates").set_defaults(func=_cmd_init)

    run_parser = sub.add_parser("run", help="run one discovery+application cycle")
    run_parser.add_argument("--dry-run", action="store_true", help="discover and score jobs, but don't apply")
    run_parser.add_argument("--headed", action="store_true", help="show the browser window (default: headless)")
    run_parser.set_defaults(func=_cmd_run)

    sub.add_parser("report", help="reprint the most recent run's summary").set_defaults(func=_cmd_report)
    sub.add_parser("pending", help="list application questions waiting on you").set_defaults(func=_cmd_pending)

    answer_parser = sub.add_parser("answer", help="answer a pending question")
    answer_parser.add_argument("id", type=int)
    answer_parser.add_argument("answer")
    answer_parser.set_defaults(func=_cmd_answer)

    sub.add_parser("schedule", help="show the cron expression for your configured search frequency").set_defaults(
        func=_cmd_schedule
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
