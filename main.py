from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from .config import load_config
from .engine import IntentionMigrationEngine


def build_engine():
    return IntentionMigrationEngine


def load_runtime_config():
    return load_config()


def _elapsed(started: float) -> float:
    return round(time.perf_counter() - started, 3)


def _line(event: str, **fields: Any) -> str:
    parts = [f"[ITMWeb] {event}"]
    parts.extend(f"{key}={value}" for key, value in fields.items())
    return "  ".join(parts)


def _trace_run(payload: dict[str, Any]) -> dict[str, Any]:
    trace = payload.get("trace") if isinstance(payload, dict) else {}
    if not isinstance(trace, dict):
        return {}
    old_trace = trace.get("old_trace")
    return old_trace if isinstance(old_trace, dict) else {}


def _order_key(path: Path) -> tuple[int, str]:
    prefix = path.stem.split("_", 1)[0]
    return (int(prefix) if prefix.isdigit() else 999999, path.name.lower())


def _scripts(root: str, start_index: int | None = None, limit: int | None = None) -> list[Path]:
    path = Path(root).resolve()
    if path.is_file():
        scripts = [path]
    elif any(path.glob("*.py")):
        scripts = sorted(path.glob("*.py"), key=_order_key)
    else:
        scripts = []
        for app in sorted([item for item in path.iterdir() if item.is_dir()], key=lambda item: item.name.lower()):
            scripts.extend(sorted(app.glob("*.py"), key=_order_key))
    if start_index is not None:
        scripts = scripts[max(0, start_index - 1) :]
    if limit is not None:
        scripts = scripts[:limit]
    return scripts


def _refresh(engine: IntentionMigrationEngine, reports: list[Any], include_replay: bool = False) -> dict[str, Path]:
    return engine.reporter.export_suite_bundle(
        reports,
        include_trace=False,
        include_migration=True,
        include_replay=include_replay,
    )


def run_migration(target: str, limit: int | None = None, start_app: str | None = None, start_index: int | None = None) -> None:
    del start_app
    started = time.perf_counter()
    engine = build_engine()(load_runtime_config())
    scripts = _scripts(target, start_index, limit)
    print(_line("migration_start", total_cases=len(scripts)))
    reports = []
    for index, script in enumerate(scripts, start=1):
        print(_line("migration_case_start", index=f"{index}/{len(scripts)}", case=script.stem))
        report = engine.migrate_case(str(script))
        reports.append(report)
        _refresh(engine, reports)
        print(
            _line(
                "migration_case_end",
                case=report.case_id,
                status=report.migration_status,
                repairs=report.repair_count,
                seconds=report.migration_duration_seconds,
            )
        )
    print(_line("migration_end", reports=len(reports), seconds=_elapsed(started)))


def run_trace(target: str, limit: int | None = None, start_app: str | None = None, start_index: int | None = None) -> None:
    del start_app
    started = time.perf_counter()
    engine = build_engine()(load_runtime_config())
    scripts = _scripts(target, start_index, limit)
    reports = []
    print(_line("trace_start", total_cases=len(scripts)))
    for index, script in enumerate(scripts, start=1):
        print(_line("trace_case_start", index=f"{index}/{len(scripts)}", case=script.stem))
        payload = engine.trace_case(str(script))
        reports.append(engine.reporter._case_payload if False else payload)
        engine.reporter.export_suite_bundle_from_payloads(
            reports,
            include_trace=True,
            include_migration=False,
            include_replay=False,
        )
        trace_run = _trace_run(payload)
        trace_status = trace_run.get("status") or ("passed" if payload.get("migration_success") else "failed")
        print(
            _line(
                "trace_case_end",
                case=script.stem,
                status=trace_status,
                seconds=trace_run.get("duration_seconds", payload.get("migration_duration_seconds", 0)),
            )
        )
        if not bool(payload.get("migration_success")):
            print(_line("trace_failed_stop", case=script.stem, status=trace_status))
            raise SystemExit(1)
    print(_line("trace_end", cases=len(reports), seconds=_elapsed(started)))


def run_replay(target: str, limit: int | None = None, start_app: str | None = None, start_index: int | None = None) -> None:
    del start_app
    started = time.perf_counter()
    engine = build_engine()(load_runtime_config())
    scripts = _scripts(target, start_index, limit)
    reports = []
    print(_line("replay_start", total_cases=len(scripts)))
    for index, script in enumerate(scripts, start=1):
        print(_line("replay_case_start", index=f"{index}/{len(scripts)}", case=script.stem))
        replay_script = engine.artifacts.case_stage_dir(script.stem, script.parent.name, "replay") / f"migrated_{script.name}"
        if not replay_script.exists():
            print(_line("replay_case_end", case=script.stem, status="skipped", success=False, seconds=0, reason="missing_migrated_script"))
            continue
        result = engine.replay_runner.replay(replay_script)
        payload = {
            "case_id": script.stem,
            "trace": {"context": {"suite_name": script.parent.name}},
            "replay": result.to_dict(),
        }
        engine.reporter.export_case_payload(script.stem, script.parent.name, payload)
        reports.append(payload)
        engine.reporter.export_suite_bundle_from_payloads(
            reports,
            include_trace=False,
            include_migration=False,
            include_replay=True,
        )
        print(
            _line(
                "replay_case_end",
                case=script.stem,
                status="passed" if result.success else "failed",
                seconds=round(result.duration_seconds, 3),
            )
        )
    print(_line("replay_end", cases=len(reports), seconds=_elapsed(started)))


def run_suite(test_root: str, limit: int | None = None, start_app: str | None = None, start_index: int | None = None) -> None:
    del start_app
    started = time.perf_counter()
    engine = build_engine()(load_runtime_config())
    scripts = _scripts(test_root, start_index, limit)
    reports = []
    print(_line("suite_start", total_cases=len(scripts)))
    for index, script in enumerate(scripts, start=1):
        print(_line("suite_case_start", index=f"{index}/{len(scripts)}", case=script.stem))
        report = engine.migrate_case(str(script))
        replay_script = Path(report.migrated_script_path)
        if replay_script.exists():
            report.replay = engine.replay_runner.replay(replay_script)
        reports.append(report)
        engine.reporter.export_case(report)
        _refresh(engine, reports, include_replay=True)
        print(
            _line(
                "suite_case_end",
                case=report.case_id,
                migration=report.migration_success,
                replay=bool(report.replay and report.replay.success),
            )
        )
    print(_line("suite_end", reports=len(reports), seconds=_elapsed(started)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal ITMWeb migration runner.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ["trace", "migration", "suite", "replay"]:
        sub = subparsers.add_parser(name)
        sub.add_argument("target")
        sub.add_argument("--limit", type=int)
        sub.add_argument("--start-index", type=int)
        sub.add_argument("--start-app")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "migration":
        run_migration(args.target, args.limit, args.start_app, args.start_index)
    elif args.command == "trace":
        run_trace(args.target, args.limit, args.start_app, args.start_index)
    elif args.command == "suite":
        run_suite(args.target, args.limit, args.start_app, args.start_index)
    elif args.command == "replay":
        run_replay(args.target, args.limit, args.start_app, args.start_index)
    else:
        raise SystemExit(json.dumps({"error": f"unknown command: {args.command}"}))


if __name__ == "__main__":
    main()
