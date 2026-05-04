from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .schemas import CaseReport


@dataclass(slots=True)
class ArtifactManager:
    config: ProjectConfig

    def _segment(self, value: str, fallback: str) -> str:
        text = (value or fallback).strip() or fallback
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("._") or fallback

    def case_dir(self, case_id: str, suite_name: str = "") -> Path:
        path = self.config.artifact_root / self._segment(suite_name, "unknown_app") / self._segment(case_id, "unknown_case")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def case_stage_dir(self, case_id: str, suite_name: str, stage: str) -> Path:
        path = self.case_dir(case_id, suite_name) / self._segment(stage, "stage")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def case_report_path(self, script_path: str | Path, case_id: str | None = None, suite_name: str = "") -> Path:
        path = Path(script_path)
        return self.case_stage_dir(case_id or path.stem, suite_name or path.parent.name, "report") / "case_report.json"

    def bootstrap_dir(self, bootstrap_dir_name: str) -> Path:
        path = self.config.artifact_root / "_bootstrap" / self._segment(bootstrap_dir_name, "runtime")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_csv_rows(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        fieldnames = list(rows[0].keys())
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def upsert_csv_rows(
        self,
        path: Path,
        rows: list[dict[str, Any]],
        fieldnames: list[str] | None = None,
        key: str = "case_name",
    ) -> None:
        del key
        if fieldnames:
            rows = [{name: row.get(name, "") for name in fieldnames} for row in rows]
        self.write_csv_rows(path, rows)


@dataclass(slots=True)
class ReportExporter:
    artifacts: ArtifactManager

    def export_case(self, report: CaseReport) -> Path:
        path = self.artifacts.case_stage_dir(report.case_id, report.trace.context.suite_name, "report") / "case_report.json"
        self.artifacts.write_json(path, self._case_payload(report))
        return path

    def export_suite_bundle(
        self,
        reports: list[CaseReport],
        suite_replay: dict[str, Any] | None = None,
        include_trace: bool = True,
        include_migration: bool = True,
        include_replay: bool = True,
    ) -> dict[str, Path]:
        del suite_replay
        payloads = [self._case_payload(report) for report in reports]
        return self.export_suite_bundle_from_payloads(payloads, include_trace, include_migration, include_replay)

    def export_suite_bundle_from_payloads(
        self,
        payloads: list[dict[str, Any]],
        suite_replay: dict[str, Any] | None = None,
        include_trace: bool = True,
        include_migration: bool = True,
        include_replay: bool = True,
    ) -> dict[str, Path]:
        del suite_replay
        root = self.artifacts.config.artifact_root
        paths = {
            "trace_csv": root / "trace.csv",
            "migration_csv": root / "migration.csv",
            "replay_csv": root / "replay.csv",
        }
        if include_trace:
            self.artifacts.write_csv_rows(paths["trace_csv"], self._trace_rows(payloads))
        if include_migration:
            self.artifacts.write_csv_rows(paths["migration_csv"], self._migration_rows(payloads))
        if include_replay:
            self.artifacts.write_csv_rows(paths["replay_csv"], self._replay_rows(payloads))
        return paths

    def export_trace_bundle(self, reports: list[CaseReport]) -> dict[str, Path]:
        payloads = [self._case_payload(report) for report in reports]
        path = self.artifacts.config.artifact_root / "trace.csv"
        self.artifacts.write_csv_rows(path, self._trace_rows(payloads))
        return {"trace_csv": path}

    def _case_payload(self, report: CaseReport) -> dict[str, Any]:
        context = report.trace.context
        replay = report.replay.to_dict() if report.replay else None
        return {
            "case_id": report.case_id,
            "trace": {
                "context": context.to_dict(),
                "failure": report.trace.failure.to_dict(),
                "snapshot": {
                    "url": report.trace.snapshot.url,
                    "title": report.trace.snapshot.title,
                    "interactable_count": len(report.trace.snapshot.interactables),
                },
            },
            "migration_status": report.migration_status,
            "migration_success": report.migration_success,
            "migration_duration_seconds": report.migration_duration_seconds,
            "repair_count": report.repair_count,
            "migration": {
                "status": report.migration_status,
                "success": report.migration_success,
                "script_path": report.migrated_script_path,
                "patch": report.patch.to_dict() if report.patch else None,
                "attempts": [item.to_dict() for item in report.round_history],
            },
            "replay": replay,
            "llm": {
                "provider": report.llm_provider,
                "remote_calls": report.llm_remote_calls,
                "seconds": round(sum(float(v or 0) for v in report.llm_task_seconds.values()), 3),
            },
        }

    def _case_name(self, payload: dict[str, Any]) -> str:
        context = payload.get("trace", {}).get("context", {})
        return f"{context.get('suite_name', '')}/{payload.get('case_id', '')}"

    def _trace_rows(self, payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for payload in payloads:
            old_trace = payload.get("trace", {}).get("old_trace") or {}
            rows.append(
                {
                    "case_name": self._case_name(payload),
                    "trace_success": old_trace.get("success", payload.get("migration_success", "")),
                    "trace_seconds": old_trace.get("duration_seconds", payload.get("migration_duration_seconds", "")),
                }
            )
        return rows

    def _migration_rows(self, payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "case_name": self._case_name(payload),
                "migration_status": payload.get("migration_status", ""),
                "migration_success": payload.get("migration_success", False),
                "migration_seconds": payload.get("migration_duration_seconds", 0.0),
                "repair_count": payload.get("repair_count", 0),
                "llm_remote_calls": payload.get("llm", {}).get("remote_calls", 0),
                "llm_seconds": payload.get("llm", {}).get("seconds", 0),
            }
            for payload in payloads
        ]

    def _replay_rows(self, payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for payload in payloads:
            replay = payload.get("replay") or payload.get("migration", {}).get("replay") or {}
            rows.append(
                {
                    "case_name": self._case_name(payload),
                    "replay_status": "passed" if replay.get("success") else ("failed" if replay else "not_run"),
                    "replay_success": bool(replay.get("success", False)),
                    "replay_seconds": replay.get("duration_seconds", 0.0),
                }
            )
        return rows
