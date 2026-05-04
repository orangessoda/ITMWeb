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

    @property
    def artifact_root(self) -> Path:
        root = getattr(self.config, "artifact_root", None)
        if root is None and hasattr(self.config, "artifacts"):
            root = getattr(self.config.artifacts, "artifact_root", None)
        return Path(root or "output")

    def _segment(self, value: str, fallback: str) -> str:
        text = (value or fallback).strip() or fallback
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("._") or fallback

    def case_dir(self, case_id: str, suite_name: str = "") -> Path:
        path = self.artifact_root / self._segment(suite_name, "unknown_app") / self._segment(case_id, "unknown_case")
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
        path = self.artifact_root / "_bootstrap" / self._segment(bootstrap_dir_name, "runtime")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_json(self, path: Path) -> Any:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

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
        path.parent.mkdir(parents=True, exist_ok=True)
        if not rows and not path.exists():
            self.write_csv_rows(path, rows)
            return
        existing_rows: list[dict[str, Any]] = []
        if path.exists() and path.read_text(encoding="utf-8").strip():
            with path.open("r", newline="", encoding="utf-8") as handle:
                existing_rows = list(csv.DictReader(handle))
        if fieldnames is None:
            names: list[str] = []
            for row in existing_rows + rows:
                for name in row.keys():
                    if name not in names:
                        names.append(name)
            fieldnames = names
        normalized_existing = [{name: row.get(name, "") for name in fieldnames} for row in existing_rows]
        normalized_new = [{name: row.get(name, "") for name in fieldnames} for row in rows]
        merged: list[dict[str, Any]] = []
        index_by_key: dict[str, int] = {}
        for row in normalized_existing:
            row_key = str(row.get(key, "") or "")
            if row_key:
                index_by_key[row_key] = len(merged)
            merged.append(row)
        for row in normalized_new:
            row_key = str(row.get(key, "") or "")
            if row_key and row_key in index_by_key:
                merged[index_by_key[row_key]] = row
            else:
                if row_key:
                    index_by_key[row_key] = len(merged)
                merged.append(row)
        self.write_csv_rows(path, merged)


@dataclass(slots=True)
class ReportExporter:
    artifacts: ArtifactManager

    def export_case(self, report: CaseReport) -> Path:
        path = self.artifacts.case_stage_dir(report.case_id, report.trace.context.suite_name, "report") / "case_report.json"
        payload = self._merge_case_payload(self.artifacts.read_json(path), self._case_payload(report))
        self.artifacts.write_json(path, payload)
        if payload.get("migration_status") != "trace_only" and payload.get("migration"):
            self.artifacts.upsert_csv_rows(
                self.artifacts.artifact_root / "migration.csv",
                self._migration_rows([payload]),
                key="case_name",
            )
        return path

    def export_case_payload(self, case_id: str, suite_name: str, payload: dict[str, Any]) -> Path:
        path = self.artifacts.case_stage_dir(case_id, suite_name, "report") / "case_report.json"
        merged = self._merge_case_payload(self.artifacts.read_json(path), payload)
        self.artifacts.write_json(path, merged)
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
        root = self.artifacts.artifact_root
        paths = {
            "trace_csv": root / "trace.csv",
            "migration_csv": root / "migration.csv",
            "replay_csv": root / "replay.csv",
        }
        if include_trace:
            self.artifacts.upsert_csv_rows(paths["trace_csv"], self._trace_rows(payloads), key="case_name")
        if include_migration:
            self.artifacts.upsert_csv_rows(paths["migration_csv"], self._migration_rows(payloads), key="case_name")
        if include_replay:
            self.artifacts.upsert_csv_rows(paths["replay_csv"], self._replay_rows(payloads), key="case_name")
        return paths

    def export_trace_bundle(self, reports: list[CaseReport]) -> dict[str, Path]:
        payloads = [self._case_payload(report) for report in reports]
        path = self.artifacts.artifact_root / "trace.csv"
        self.artifacts.upsert_csv_rows(path, self._trace_rows(payloads), key="case_name")
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
                "old_trace_intentions": dict(report.trace.old_trace_intentions),
                "old_trace": self._old_trace_summary(report.trace.old_trace),
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

    def _old_trace_summary(self, old_trace: Any) -> dict[str, Any] | None:
        if old_trace is None:
            return None
        return {
            "label": old_trace.label,
            "environment": old_trace.environment,
            "script_path": old_trace.script_path,
            "status": old_trace.status,
            "success": old_trace.success,
            "return_code": old_trace.return_code,
            "duration_seconds": old_trace.duration_seconds,
            "log_path": old_trace.log_path,
            "stdout_tail": old_trace.stdout_tail,
            "stderr_tail": old_trace.stderr_tail,
            "error_type": old_trace.error_type,
            "failure_message": old_trace.failure_message,
            "actions_count": len(old_trace.actions or []),
            "recorded_at": old_trace.recorded_at,
            "metadata": dict(old_trace.metadata or {}),
        }

    def _merge_case_payload(self, existing: Any, incoming: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(existing, dict):
            return incoming
        merged = dict(existing)
        merged["case_id"] = incoming.get("case_id", merged.get("case_id", ""))

        stage = self._payload_stage(incoming)
        if stage == "trace":
            merged["trace"] = incoming.get("trace", merged.get("trace", {}))
            for key in ["migration", "replay", "llm"]:
                if key not in merged and incoming.get(key) not in (None, {}, []):
                    merged[key] = incoming[key]
            for key in ["migration_status", "migration_success", "migration_duration_seconds", "repair_count"]:
                if key not in merged and key in incoming:
                    merged[key] = incoming[key]
            return merged

        if stage in {"migration", "suite"}:
            if "trace" not in merged or not merged.get("trace"):
                merged["trace"] = incoming.get("trace", {})
            for key in ["migration_status", "migration_success", "migration_duration_seconds", "repair_count", "migration", "llm"]:
                if key in incoming:
                    merged[key] = incoming[key]
            if stage == "suite" and incoming.get("replay") is not None:
                merged["replay"] = incoming["replay"]
            return merged

        if stage == "replay":
            if "trace" not in merged and incoming.get("trace"):
                merged["trace"] = incoming["trace"]
            merged["replay"] = incoming.get("replay")
            return merged

        return {**merged, **incoming}

    def _payload_stage(self, payload: dict[str, Any]) -> str:
        if payload.get("replay") is not None and not payload.get("migration"):
            return "replay"
        if payload.get("replay") is not None and payload.get("migration"):
            return "suite"
        if payload.get("migration_status") == "trace_only":
            return "trace"
        if payload.get("migration"):
            return "migration"
        return "unknown"

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
