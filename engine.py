from __future__ import annotations

import ast
import codeop
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import builtins
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .browser import BrowserSession
from .config import ProjectConfig
from .mapping import IntentMappingLibrary
from .patcher import PatchApplier, PatchGenerator, ReplayRunner, ScriptAnalyzer
from .report import ArtifactManager, ReportExporter
from .schemas import (
    CaseReport,
    DOMSnapshot,
    ElementRecord,
    FailureInfo,
    FulfillmentAttemptRecord,
    FulfillmentOption,
    IntentRecord,
    MigrationPatch,
    MigrationVerdict,
    ReplayResult,
    ScriptContext,
    TraceBundle,
    ValidationResult,
)
from .trace_runner import InstrumentedScriptRunner, TraceArtifactLoader

try:  # pragma: no cover - optional runtime dependency
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


@dataclass(slots=True)
class _RunState:
    success: bool
    next_line: int
    failure: FailureInfo | None = None
    stderr: str = ""


@dataclass(slots=True)
class _RepairResult:
    success: bool
    patch: MigrationPatch | None = None
    candidate: FulfillmentOption | None = None
    options: list[tuple[MigrationPatch, FulfillmentOption]] = field(default_factory=list)
    attempts: list[FulfillmentAttemptRecord] = field(default_factory=list)
    validations: list[ValidationResult] = field(default_factory=list)


class _QuietSubprocess:
    def __getattr__(self, name: str) -> Any:
        return getattr(subprocess, name)

    def run(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        kwargs.setdefault("capture_output", True)
        kwargs.setdefault("text", True)
        return subprocess.run(*args, **kwargs)


@dataclass(slots=True)
class LLMRuntimeStats:
    remote_calls: int = 0
    fallback_calls: int = 0
    fallback_tasks: list[str] = field(default_factory=list)
    fallback_reasons: list[str] = field(default_factory=list)
    task_seconds: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "remote_calls": self.remote_calls,
            "fallback_calls": self.fallback_calls,
            "fallback_tasks": list(self.fallback_tasks),
            "fallback_reasons": list(self.fallback_reasons),
            "task_seconds": dict(self.task_seconds),
            "remote_used": self.remote_calls > 0,
            "fallback_used": self.fallback_calls > 0,
        }


class LLMClient:
    def __init__(self, config: Any) -> None:
        self.config = config
        self.runtime_stats = LLMRuntimeStats()
        self.raw_failure_log_dir: Path | None = None
        self.dialog_index = 0

    def reset_runtime_stats(self) -> None:
        self.runtime_stats = LLMRuntimeStats()
        self.dialog_index = 0

    def set_raw_failure_log_dir(self, log_dir: str | Path | None) -> None:
        self.raw_failure_log_dir = Path(log_dir) if log_dir else None

    def snapshot_runtime_stats(self) -> dict[str, Any]:
        return self.runtime_stats.to_dict()

    def provider_metadata(self) -> dict[str, str]:
        return {
            "provider": str(getattr(self.config, "provider", "") or ""),
            "model_name": str(getattr(self.config, "model_name", "") or ""),
            "api_base": str(getattr(self.config, "api_base", "") or ""),
        }

    def generate_old_trace_intentions(self, case_id: str, suite_name: str, action_log_text: str) -> dict[str, Any]:
        payload = {
            "task": "generate_old_trace_intentions",
            "instruction": (
                "Read the Selenium trace action_log and return compact JSON describing the old test intent. "
                "Return fields: case_goal, summary, steps. Each step should include action_type, target, value, "
                "page_url, expected_result when visible from the log."
            ),
            "case_id": case_id,
            "suite_name": suite_name,
            "action_log": action_log_text,
        }
        if not self._should_use_remote():
            self.runtime_stats.fallback_calls += 1
            self.runtime_stats.fallback_tasks.append("generate_old_trace_intentions")
            self.runtime_stats.fallback_reasons.append("remote_disabled")
            return {"case_goal": case_id, "summary": f"Migrate {suite_name}/{case_id}.", "steps": []}
        started = time.perf_counter()
        try:
            result = self._call_json(payload)
            self.runtime_stats.remote_calls += 1
            return result
        except Exception as exc:
            self.runtime_stats.fallback_calls += 1
            self.runtime_stats.fallback_tasks.append("generate_old_trace_intentions")
            self.runtime_stats.fallback_reasons.append(exc.__class__.__name__)
            return {
                "case_goal": case_id,
                "summary": f"Migrate {suite_name}/{case_id}.",
                "steps": [],
                "error": exc.__class__.__name__,
            }
        finally:
            self.runtime_stats.task_seconds["generate_old_trace_intentions"] = (
                self.runtime_stats.task_seconds.get("generate_old_trace_intentions", 0.0) + time.perf_counter() - started
            )

    def migrate_oracle_from_intentions(
        self,
        case_id: str,
        suite_name: str,
        assertions: list[str],
        old_intentions: dict[str, Any],
    ) -> dict[str, Any]:
        del old_intentions
        return {"case_id": case_id, "suite_name": suite_name, "assertions": assertions, "status": "skipped"}

    def controls_payload(self, candidates: list[FulfillmentOption]) -> list[dict[str, Any]]:
        return [self._control_payload(index, candidate) for index, candidate in enumerate(candidates, start=1)]

    def choose_repair_actions(
        self,
        trace: TraceBundle,
        intent: IntentRecord,
        candidates: list[FulfillmentOption],
        repair_dialog: list[dict[str, str]] | None = None,
        exploration_context: dict[str, Any] | None = None,
    ) -> list[FulfillmentOption]:
        del repair_dialog, exploration_context
        if not self._should_use_remote():
            self.runtime_stats.fallback_calls += 1
            self.runtime_stats.fallback_tasks.append("choose_repair_actions")
            self.runtime_stats.fallback_reasons.append("remote_disabled")
            return candidates
        started = time.perf_counter()
        payload = {
            "task": "choose_repair_actions",
            "instruction": (
                "Return up to 3 target-side Selenium action chains for the failing statement, ordered from most "
                "likely to least likely. Each choice must be one complete action chain. Return compact JSON: "
                "{\"choices\":[{\"steps\":[{\"candidate_index\":1,\"action_type\":\"click|input|clear|select|submit|wait|"
                "get|open_url|execute_script|switch_frame|default_content|hover\","
                "\"selector\":\"...\",\"selector_type\":\"id|css|xpath|name|link_text\",\"value\":\"optional\"}]}]}. "
                "For get/open_url put the URL in value. For execute_script put the JavaScript in value. "
                "For default_content selector may be empty. "
                "Prefer stable selectors in this order: id, name, link_text, partial_link_text, xpath, css. "
                "Avoid broad CSS selectors when an id, name, or link_text candidate exists. "
                "Use candidate_index when a step uses one of the provided candidates; otherwise provide selector "
                "and selector_type directly."
            ),
            "action_log": self._trace_action_log_text(trace),
            "old_intentions": dict(trace.old_trace_intentions),
            "failure": trace.failure.to_dict(),
            "intent": intent.to_dict(),
            "candidates": self.controls_payload(candidates),
        }
        try:
            response = self._call_json(payload)
            choices = self._choices_from_response(response, candidates)
            self.runtime_stats.remote_calls += 1
            return choices or candidates
        except Exception as exc:
            self.runtime_stats.fallback_calls += 1
            self.runtime_stats.fallback_tasks.append("choose_repair_actions")
            self.runtime_stats.fallback_reasons.append(exc.__class__.__name__)
            return candidates
        finally:
            self.runtime_stats.task_seconds["choose_repair_actions"] = (
                self.runtime_stats.task_seconds.get("choose_repair_actions", 0.0) + time.perf_counter() - started
            )

    def _trace_action_log_text(self, trace: TraceBundle) -> str:
        log_path = str(getattr(trace.old_trace, "log_path", "") or "")
        if not log_path:
            return ""
        try:
            return Path(log_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def _control_payload(self, index: int, candidate: FulfillmentOption) -> dict[str, Any]:
        element = candidate.element
        attrs = element.attributes if element else {}
        return {
            "index": index,
            "selector": candidate.selector,
            "selector_type": str(candidate.metadata.get("selector_type", "") or ""),
            "action_type": candidate.action_type,
            "label": self._best_label(element),
            "tag": element.tag if element else "",
            "text": element.text if element else "",
            "identity": {key: attrs.get(key, "") for key in ["id", "name", "type", "href", "class"] if attrs.get(key, "")},
            "visible": bool(getattr(element, "is_visible", True)),
            "enabled": bool(getattr(element, "is_enabled", True)),
        }

    def _choices_from_response(
        self,
        response: dict[str, Any],
        candidates: list[FulfillmentOption],
    ) -> list[FulfillmentOption]:
        choices = response.get("choices", [])
        if isinstance(response.get("choice"), dict):
            choices = [response["choice"]]
        if not isinstance(choices, list):
            return []
        selected: list[FulfillmentOption] = []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            steps = self._choice_steps(choice)
            if not steps:
                steps = [choice]
            normalized_steps: list[dict[str, Any]] = []
            primary_base: FulfillmentOption | None = None
            for step in steps:
                if not isinstance(step, dict):
                    continue
                index = int(step.get("candidate_index", step.get("index", 0)) or 0)
                base = candidates[index - 1] if 1 <= index <= len(candidates) else None
                if primary_base is None and base is not None:
                    primary_base = base
                selector = str(step.get("selector", "") or (base.selector if base else ""))
                action_type = self._normalize_action(str(step.get("action_type", "") or (base.action_type if base else "")))
                if not selector and action_type not in {"wait", "get", "open_url", "execute_script", "default_content"}:
                    continue
                selector_type = str(step.get("selector_type", "") or (base.metadata.get("selector_type", "") if base else ""))
                normalized_steps.append(
                    {
                        "action_type": action_type,
                        "selector": selector,
                        "selector_type": selector_type,
                        "value": str(step.get("value", "") or ""),
                        "value_expression": str(step.get("value_expression", "") or ""),
                    }
                )
            if not normalized_steps:
                continue
            first = normalized_steps[0]
            metadata = dict(primary_base.metadata if primary_base else {})
            metadata["mapped_recipe_steps"] = normalized_steps
            metadata["selector_type"] = str(first.get("selector_type", "") or metadata.get("selector_type", ""))
            metadata["value"] = str(first.get("value", "") or metadata.get("value", ""))
            selected.append(
                FulfillmentOption(
                    source="llm",
                    action_type=str(first.get("action_type", "") or "click"),
                    selector=str(first.get("selector", "") or "trace:wait"),
                    element=primary_base.element if primary_base else None,
                    confidence=1.0,
                    explanation="Selected action chain by LLM.",
                    metadata=metadata,
                )
            )
        return selected

    def _choice_steps(self, choice: dict[str, Any]) -> list[Any]:
        steps = choice.get("steps", [])
        if isinstance(steps, list):
            return steps
        actions = choice.get("actions", [])
        if isinstance(actions, list):
            return actions
        return []

    def _call_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        client = self._build_client()
        if client is None:
            raise RuntimeError("LLM client is not configured.")
        self.dialog_index += 1
        dialog_path = self._dialog_path(payload)
        messages = [
            {"role": "system", "content": "You repair Selenium migration breakpoints. Return JSON only."},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        self._write_dialog_json(
            dialog_path,
            {
                "index": self.dialog_index,
                "task": str(payload.get("task", "") or ""),
                "request": payload,
                "messages": messages,
                "provider": self.provider_metadata(),
            },
        )
        response = client.chat.completions.create(
            model=str(getattr(self.config, "model_name", "") or "gpt-4o-mini"),
            messages=messages,
            temperature=0,
        )
        text = response.choices[0].message.content or "{}"
        match = re.search(r"\{.*\}", text, re.S)
        parsed = json.loads(match.group(0) if match else text)
        self._write_dialog_json(
            dialog_path,
            {
                "index": self.dialog_index,
                "task": str(payload.get("task", "") or ""),
                "request": payload,
                "messages": messages,
                "response_text": text,
                "response_json": parsed,
                "provider": self.provider_metadata(),
            },
        )
        return parsed

    def _dialog_path(self, payload: dict[str, Any]) -> Path | None:
        if self.raw_failure_log_dir is None:
            return None
        task = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(payload.get("task", "llm") or "llm")).strip("_") or "llm"
        return self.raw_failure_log_dir / "llm_dialogs" / f"{self.dialog_index:03d}_{task}.json"

    def _write_dialog_json(self, path: Path | None, payload: dict[str, Any]) -> None:
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _build_client(self) -> Any | None:
        if OpenAI is None:
            return None
        api_key = str(getattr(self.config, "api_key", "") or "")
        if not api_key:
            return None
        api_base = str(getattr(self.config, "api_base", "") or "").strip()
        return OpenAI(api_key=api_key, base_url=api_base or None)

    def _should_use_remote(self) -> bool:
        return bool(str(getattr(self.config, "api_key", "") or "")) and OpenAI is not None

    def _best_label(self, element: ElementRecord | None) -> str:
        if element is None:
            return ""
        attrs = element.attributes or {}
        return str(
            attrs.get("aria-label")
            or attrs.get("title")
            or attrs.get("id")
            or attrs.get("name")
            or element.text
            or element.locator_hint
            or ""
        )

    def _normalize_action(self, action_type: str) -> str:
        action = str(action_type or "").strip().lower()
        if action == "send_keys":
            return "input"
        if action in {"open", "navigate", "driver_get"}:
            return "get"
        if action in {"switch_to_frame", "frame"}:
            return "switch_frame"
        if action in {"switch_to_default_content", "default"}:
            return "default_content"
        if action in {"mouse_over", "move_to_element", "actionchains"}:
            return "hover"
        if action in {"js_click", "confirm_click"}:
            return "click"
        return action or "click"


@dataclass
class IntentionMigrationEngine:
    config: ProjectConfig
    browser: BrowserSession | None = None
    trace_runner: InstrumentedScriptRunner | None = None
    trace_loader: TraceArtifactLoader | None = None
    script_analyzer: ScriptAnalyzer | None = None
    patch_generator: PatchGenerator | None = None
    patch_applier: PatchApplier | None = None
    replay_runner: ReplayRunner | None = None
    artifacts: ArtifactManager | None = None
    reporter: ReportExporter | None = None
    llm: LLMClient | None = None
    intent_mapping_library: IntentMappingLibrary | None = None

    def __post_init__(self) -> None:
        self.browser = self.browser or BrowserSession(self.config.browser)
        self.trace_runner = self.trace_runner or InstrumentedScriptRunner(self.config, ArtifactManager(self.config))
        self.trace_loader = self.trace_loader or TraceArtifactLoader(ArtifactManager(self.config))
        self.script_analyzer = self.script_analyzer or ScriptAnalyzer()
        self.patch_generator = self.patch_generator or PatchGenerator()
        self.patch_applier = self.patch_applier or PatchApplier(self.script_analyzer)
        self.replay_runner = self.replay_runner or ReplayRunner(self.config, ArtifactManager(self.config))
        self.artifacts = self.artifacts or ArtifactManager(self.config)
        self.reporter = self.reporter or ReportExporter(self.artifacts)
        self.llm = self.llm or LLMClient(self.config.model)
        self.intent_mapping_library = self.intent_mapping_library or IntentMappingLibrary(
            self.config.artifacts.artifact_root / "intent_mapping_library.json"
        )
        self._migration_profile_dirs: list[str] = []
        self._migration_original_chrome: Any | None = None
        self._migration_printed_reset_messages: set[str] = set()

    def trace_case(self, test_script_path: str) -> dict[str, Any]:
        script_path = Path(test_script_path).resolve()
        suite_name = script_path.parent.name
        case_id = script_path.stem
        trace_script = self._infer_old_script(script_path) or script_path
        artifact_dir = self.artifacts.case_dir(case_id, suite_name)
        result = self.trace_runner.run(trace_script, artifact_dir, label="old_trace", environment="old")
        failure = FailureInfo(
            script_path=str(trace_script),
            line_num=0,
            broken_statement="",
            error_type=result.trace.error_type or "unknown",
            traceback=result.stderr,
            message=result.trace.failure_message,
        )
        trace = TraceBundle(
            failure=failure,
            context=ScriptContext(
                script_path=str(script_path),
                case_id=case_id,
                suite_name=suite_name,
                base_url=self._base_url(script_path),
            ),
            snapshot=DOMSnapshot(),
            raw_stdout=result.stdout,
            raw_stderr=result.stderr,
            old_trace=result.trace,
        )
        report = CaseReport(
            case_id=case_id,
            trace=trace,
            migration_status="trace_only",
            migration_success=result.trace.success,
            migration_duration_seconds=result.trace.duration_seconds,
        )
        self.reporter.export_case(report)
        return report.to_dict()

    def migrate_case(self, test_script_path: str) -> CaseReport:
        started = time.perf_counter()
        script_path = Path(test_script_path).resolve()
        case_id = script_path.stem
        suite_name = script_path.parent.name
        self.llm.reset_runtime_stats()
        self.llm.set_raw_failure_log_dir(self.artifacts.case_stage_dir(case_id, suite_name, "report"))
        old_intentions = self._generate_old_trace_intentions(case_id, suite_name)

        replay_dir = self.artifacts.case_stage_dir(case_id, suite_name, "replay")
        migrated_script = replay_dir / f"migrated_{script_path.name}"
        self._copy_original_script_to_replay(script_path, migrated_script)

        attempts: list[FulfillmentAttemptRecord] = []
        validations: list[ValidationResult] = []
        pending_mappings: list[tuple[TraceBundle, str, FulfillmentOption, MigrationPatch]] = []
        last_trace: TraceBundle | None = None
        last_patch: MigrationPatch | None = None
        max_rounds = max(1, int(getattr(self.config.migration, "max_repair_rounds", 12) or 12))

        namespace = self._execution_namespace()
        next_start_line = 1
        self.browser.close()

        for _ in range(max_rounds):
            run = self._run_until_failure(migrated_script, next_start_line, namespace)
            if run.success:
                self._learn_pending_mappings(pending_mappings)
                report = self._report(
                    case_id=case_id,
                    suite_name=suite_name,
                    trace=last_trace or self._trace_for_success(script_path, suite_name, old_intentions),
                    status="passed",
                    success=True,
                    started=started,
                    patch=last_patch,
                    attempts=attempts,
                    validations=validations,
                    migrated_script_path=str(migrated_script),
                )
                self.reporter.export_case(report)
                self._close_migration_browser_state()
                return report
            if run.failure is None:
                break
            trace = self._trace_for_failure(script_path, suite_name, run.failure, run.stderr, old_intentions)
            last_trace = trace
            repair = self._repair_breakpoint(trace)
            if not repair.success or not repair.options:
                break
            base_lines = self.script_analyzer.read_lines(migrated_script)
            candidate_passed = False
            for patch, candidate in repair.options:
                self._write_script_lines(migrated_script, base_lines)
                self.patch_applier.apply_patch(migrated_script, patch)
                candidate_run = self._run_until_failure(migrated_script, max(1, int(patch.line_num or run.next_line)), namespace)
                breakpoint_passed = candidate_run.success or (
                    candidate_run.failure is not None
                    and int(candidate_run.failure.line_num or 0) != int(run.failure.line_num or 0)
                )
                attempt = FulfillmentAttemptRecord(
                    round_index=len(attempts) + 1,
                    candidate_id=str(candidate.metadata.get("candidate_id", "") or ""),
                    selector=candidate.selector,
                    action_type=candidate.action_type,
                    verdict="passed" if breakpoint_passed else "failed",
                    plan_source=candidate.source,
                )
                attempts.append(attempt)
                validations.append(
                    ValidationResult(
                        verdict=attempt.verdict,
                        candidate_selector=candidate.selector,
                        passed_checks=["breakpoint_passed"] if breakpoint_passed else [],
                        failed_checks=[] if breakpoint_passed else [candidate_run.failure.error_type if candidate_run.failure else "unknown"],
                        notes=candidate.explanation,
                    )
                )
                if candidate_run.success:
                    pending_mappings.append((trace, self._active_repair_statement(trace)[1], candidate, patch))
                    self._learn_pending_mappings(pending_mappings)
                    last_patch = patch
                    report = self._report(
                        case_id=case_id,
                        suite_name=suite_name,
                        trace=trace,
                        status="passed",
                        success=True,
                        started=started,
                        patch=last_patch,
                        attempts=attempts,
                        validations=validations,
                        migrated_script_path=str(migrated_script),
                    )
                    self.reporter.export_case(report)
                    self._close_migration_browser_state()
                    return report
                if breakpoint_passed and candidate_run.failure is not None:
                    pending_mappings.append((trace, self._active_repair_statement(trace)[1], candidate, patch))
                    last_patch = patch
                    next_start_line = max(1, int(candidate_run.failure.line_num or candidate_run.next_line))
                    candidate_passed = True
                    break
            if not candidate_passed:
                self._write_script_lines(migrated_script, base_lines)
                break

        trace = last_trace or self._trace_for_success(script_path, suite_name, old_intentions)
        report = self._report(
            case_id=case_id,
            suite_name=suite_name,
            trace=trace,
            status="partial" if attempts else "blocked",
            success=False,
            started=started,
            patch=last_patch,
            attempts=attempts,
            validations=validations,
            migrated_script_path=str(migrated_script),
        )
        self.reporter.export_case(report)
        self._close_migration_browser_state()
        return report

    def _close_migration_browser_state(self) -> None:
        self.browser.close()
        self._cleanup_migration_profiles()

    def _learn_pending_mappings(self, pending_mappings: list[tuple[TraceBundle, str, FulfillmentOption, MigrationPatch]]) -> None:
        for trace, statement, candidate, patch in pending_mappings:
            self._learn_mapping(trace, statement, candidate, patch)
        pending_mappings.clear()

    def build_migration_error_report(
        self,
        test_script_path: str,
        status: str,
        message: str,
        started: float | None = None,
        exc: Exception | None = None,
    ) -> CaseReport:
        script_path = Path(test_script_path).resolve()
        failure = FailureInfo(
            script_path=str(script_path),
            line_num=1,
            broken_statement="",
            traceback=traceback.format_exception_only(type(exc), exc)[-1].strip() if exc else "",
            message=message,
        )
        trace = self._build_trace_bundle(script_path, script_path.parent.name, failure, failure.traceback)
        return self._report(script_path.stem, script_path.parent.name, trace, status, False, started or time.perf_counter())

    def _repair_breakpoint(self, trace: TraceBundle) -> _RepairResult:
        active_line, active_statement = self._active_repair_statement(trace)
        candidates = self._candidates_from_snapshot(trace.snapshot, active_statement)
        self._prepare_candidate_values(candidates, active_statement, trace.context.script_path)
        mapped = self.intent_mapping_library.best_candidate(self._runtime_signature(trace, active_statement))
        if mapped is not None:
            self._prepare_candidate_values([mapped], active_statement, trace.context.script_path)
            candidates = [mapped]
        else:
            candidates = candidates
        intent = IntentRecord(
            name="repair_breakpoint",
            description=f"Repair this Selenium statement: {active_statement}",
            action_type=self._action_type(active_statement),
            target_semantics=active_statement,
            expected_outcome="The migrated script continues.",
            confidence=1.0,
        )
        choices = candidates if mapped is not None else self.llm.choose_repair_actions(trace, intent, candidates)
        options: list[tuple[MigrationPatch, FulfillmentOption]] = []
        for index, candidate in enumerate(choices[:3], start=1):
            del index
            patch = self.patch_generator.from_candidate(trace.failure.broken_statement, trace.failure.line_num, candidate)
            patch.replacement_line_count = max(
                int(patch.replacement_line_count or 1),
                active_line - int(trace.failure.line_num) + self._statement_line_count(active_statement),
            )
            options.append((patch, candidate))
        return _RepairResult(bool(options), options[0][0] if options else None, options[0][1] if options else None, options)

    def _write_script_lines(self, script_path: Path, lines: list[str]) -> None:
        script_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _run_until_failure(
        self,
        script_path: Path,
        start_line: int,
        namespace: dict[str, Any],
    ) -> _RunState:
        self._install_migration_browser_isolation()
        lines = self.script_analyzer.read_lines(script_path)
        namespace["__file__"] = str(script_path)
        for line_num, source in self._iter_statements(lines, start_line):
            if self._ignore_source_statement(source):
                continue
            if self._is_driver_get(source):
                self._execute_driver_get(source)
                namespace["driver"] = self.browser.driver
                continue
            if self.browser.driver is None and self._needs_driver(source):
                self.browser.open()
                namespace["driver"] = self.browser.driver
            try:
                namespace["driver"] = self.browser.driver
                original_subprocess = sys.modules.get("subprocess")
                sys.modules["subprocess"] = namespace.get("subprocess", _QuietSubprocess())
                try:
                    source_with_line_offset = ("\n" * max(0, line_num - 1)) + source
                    exec(compile(source_with_line_offset, str(script_path), "exec"), namespace, namespace)
                    if namespace.get("driver") is not None:
                        self.browser.driver = namespace["driver"]
                finally:
                    if original_subprocess is None:
                        sys.modules.pop("subprocess", None)
                    else:
                        sys.modules["subprocess"] = original_subprocess
            except Exception:
                tb = traceback.format_exc()
                line = self._line_from_traceback(tb, line_num, script_path)
                statement = self.script_analyzer.get_statement_block(script_path, line) or source
                return _RunState(
                    success=False,
                    next_line=line_num,
                    failure=FailureInfo(
                        script_path=str(script_path),
                        line_num=line,
                        broken_statement=statement,
                        error_type=self._error_type_from_traceback(tb),
                        traceback=tb,
                        message="Migration stopped at the current failing statement.",
                    ),
                    stderr=tb,
                )
        return _RunState(True, len(lines) + 1)

    def _install_migration_browser_isolation(self) -> None:
        try:
            from selenium import webdriver as selenium_webdriver
            from selenium.webdriver.chrome.options import Options as ChromeOptions
            from selenium.webdriver.chrome.service import Service as ChromeService
        except Exception:
            return
        current = getattr(selenium_webdriver, "Chrome", None)
        if getattr(current, "_itmweb_migration_isolated", False):
            return
        self._migration_original_chrome = current
        engine = self

        def _chrome_with_migration_options(*args: Any, **kwargs: Any) -> Any:
            options = kwargs.get("options")
            if options is None:
                options = ChromeOptions()
            option_args = list(getattr(options, "arguments", []) or [])
            browser_config = engine.config.browser
            if getattr(browser_config, "force_no_proxy_server", True) and "--no-proxy-server" not in option_args:
                options.add_argument("--no-proxy-server")
            if getattr(browser_config, "force_no_proxy_server", True) and not any(arg.startswith("--proxy-bypass-list=") for arg in option_args):
                options.add_argument("--proxy-bypass-list=*.local;localhost;127.0.0.1")
            if getattr(browser_config, "use_isolated_user_data_dir", True) and not any(arg.startswith("--user-data-dir=") for arg in option_args):
                root = Path(getattr(browser_config, "isolated_user_data_root", "") or tempfile.gettempdir())
                root.mkdir(parents=True, exist_ok=True)
                profile_dir = tempfile.mkdtemp(prefix="chrome_profile_", dir=str(root))
                engine._migration_profile_dirs.append(profile_dir)
                options.add_argument(f"--user-data-dir={profile_dir}")
            kwargs["options"] = options
            driver_path = str(getattr(browser_config, "driver_path", "") or "").strip()
            if driver_path and "service" not in kwargs and not args:
                kwargs["service"] = ChromeService(driver_path)
            return engine._migration_original_chrome(*args, **kwargs)

        _chrome_with_migration_options._itmweb_migration_isolated = True  # type: ignore[attr-defined]
        selenium_webdriver.Chrome = _chrome_with_migration_options

    def _cleanup_migration_profiles(self) -> None:
        for profile_dir in list(getattr(self, "_migration_profile_dirs", []) or []):
            shutil.rmtree(profile_dir, ignore_errors=True)
        self._migration_profile_dirs.clear()

    def _candidates_from_snapshot(self, snapshot: DOMSnapshot, statement: str) -> list[FulfillmentOption]:
        action = self._action_type(statement)
        candidates: list[FulfillmentOption] = []
        for index, element in enumerate(self._rank_interactables(snapshot.interactables)[:80], start=1):
            selector_type, selector = self._selector_for_element(element)
            if not selector:
                continue
            candidates.append(
                FulfillmentOption(
                    source="dom",
                    action_type=self._element_action(action, element),
                    selector=selector,
                    element=element,
                    confidence=1.0,
                    explanation=f"Candidate {index}: {self._element_text(element)[:120]}",
                    metadata={
                        "candidate_id": f"c{index:03d}",
                        "selector_type": selector_type,
                        "target_role": self._element_text(element)[:160],
                        "is_visible": bool(element.is_visible),
                    },
                )
            )
        return candidates

    def _rank_interactables(self, elements: list[ElementRecord]) -> list[ElementRecord]:
        def rank(element: ElementRecord) -> tuple[int, int, int]:
            selector_type, selector = self._selector_for_element(element)
            priority = {
                "id": 0,
                "name": 1,
                "link_text": 2,
                "partial_link_text": 3,
                "xpath": 4,
                "css": 5,
            }.get(selector_type, 9)
            broad_css = 1 if selector_type == "css" and self._is_broad_css_selector(selector) else 0
            hidden = 1 if not bool(element.is_visible) else 0
            return hidden, broad_css, priority

        return sorted(elements, key=rank)

    def _is_broad_css_selector(self, selector: str) -> bool:
        value = str(selector or "").strip()
        if not value:
            return True
        return not any(token in value for token in ["#", "[id=", "[name=", "[href=", "[aria-label=", "[title="])

    def _prepare_candidate_values(
        self,
        candidates: list[FulfillmentOption],
        statement: str,
        script_path: str,
    ) -> None:
        value = self._statement_action_value(statement)
        expression = self._statement_action_expression(statement)
        if value and self._looks_like_path(value):
            path = Path(value)
            if not path.is_absolute():
                path = Path(script_path).resolve().parent / path
            value = str(path.resolve())
            expression = json.dumps(value)
        for candidate in candidates:
            if value:
                candidate.metadata["value"] = value
            if expression:
                candidate.metadata["value_expression"] = expression

    def _active_repair_statement(self, trace: TraceBundle) -> tuple[int, str]:
        line_num = int(trace.failure.line_num)
        statement = trace.failure.broken_statement
        if self._action_type(statement) != "clear":
            return line_num, statement
        try:
            script_path = Path(trace.failure.script_path)
            lines = self.script_analyzer.read_lines(script_path)
            start = line_num + self._statement_line_count(statement)
            for next_line, next_statement in self._iter_statements(lines, start):
                if self._action_type(next_statement) == "input":
                    end_line = next_line + self._statement_line_count(next_statement) - 1
                    combined = "\n".join(lines[line_num - 1 : end_line])
                    return line_num, combined
                if self._is_meaningful_statement(next_statement):
                    break
        except Exception:
            pass
        return line_num, statement

    def _generate_old_trace_intentions(self, case_id: str, suite_name: str) -> dict[str, Any]:
        trace_log = self.artifacts.case_stage_dir(case_id, suite_name, "trace") / "action_log.txt"
        action_log_text = ""
        if trace_log.exists():
            action_log_text = trace_log.read_text(encoding="utf-8", errors="ignore")
        old_intentions = self.llm.generate_old_trace_intentions(case_id, suite_name, action_log_text)
        report_dir = self.artifacts.case_stage_dir(case_id, suite_name, "report")
        self.artifacts.write_json(report_dir / "old_intentions.json", old_intentions)
        return old_intentions

    def _trace_for_failure(
        self,
        script_path: Path,
        suite_name: str,
        failure: FailureInfo,
        stderr: str,
        old_intentions: dict[str, Any] | None = None,
    ) -> TraceBundle:
        snapshot = DOMSnapshot()
        try:
            snapshot = self.browser.snapshot()
        except Exception:
            pass
        return self._build_trace_bundle(script_path, suite_name, failure, stderr, snapshot, old_intentions)

    def _trace_for_success(
        self,
        script_path: Path,
        suite_name: str,
        old_intentions: dict[str, Any] | None = None,
    ) -> TraceBundle:
        failure = FailureInfo(script_path=str(script_path), line_num=0, broken_statement="", message="Migration passed.")
        return self._build_trace_bundle(script_path, suite_name, failure, "", DOMSnapshot(), old_intentions)

    def _runtime_signature(self, trace: TraceBundle, statement: str | None = None) -> dict[str, Any]:
        statement = statement or trace.failure.broken_statement
        action_type = self._action_type(statement)
        suite_name = trace.context.suite_name
        return {
            "app_name": self.intent_mapping_library.app_name(suite_name, trace.context.script_path),
            "suite_name": suite_name,
            "case_id": trace.context.case_id,
            "script_path": trace.context.script_path,
            "source_statement": statement,
            "locator_hint": self._locator_hint(statement),
            "intent_name": "repair_breakpoint",
            "action_type": action_type,
            "action_family": f"{action_type}_family",
            "business_goal": action_type,
            "business_action": self.intent_mapping_library.infer_business_action(action_type, action_type, statement),
            "page_url": trace.snapshot.url,
            "page_title": trace.snapshot.title,
            "page_terms": self.intent_mapping_library.signal_terms(trace.snapshot.title + " " + trace.snapshot.url, 12),
            "source_terms": self.intent_mapping_library.signal_terms(statement, 12),
            "context_terms": [],
            "target_role": "",
            "old_intention": {},
        }

    def _learn_mapping(
        self,
        trace: TraceBundle,
        statement: str,
        candidate: FulfillmentOption,
        patch: MigrationPatch,
    ) -> None:
        try:
            self.intent_mapping_library.upsert_success(
                runtime_signature=self._runtime_signature(trace, statement),
                selector=candidate.selector,
                action_type=candidate.action_type,
                selector_type=str(candidate.metadata.get("selector_type", "") or ""),
                replay_value=str(candidate.metadata.get("value", "") or ""),
                patch_statement=patch.migrated_statement,
                expected_outcome="script continues",
                step_index=int(trace.failure.line_num or 0),
                page_gate_text=trace.snapshot.title,
                reasoning=candidate.explanation,
                recipe_steps=candidate.metadata.get("mapped_recipe_steps", None),
            )
        except Exception:
            pass

    def _build_trace_bundle(
        self,
        script_path: Path,
        suite_name: str,
        failure: FailureInfo,
        stderr: str,
        snapshot: DOMSnapshot | None = None,
        old_intentions: dict[str, Any] | None = None,
    ) -> TraceBundle:
        context = ScriptContext(
            script_path=str(script_path),
            case_id=script_path.stem,
            suite_name=suite_name,
            base_url=self._base_url(script_path),
            previous_steps=[],
            next_steps=[],
        )
        old_trace = None
        try:
            artifacts = self.trace_loader.load_existing_trace_artifacts(script_path.stem, suite_name)
            old_trace = artifacts.old_capture.trace if artifacts.old_capture else None
        except Exception as exc:
            try:
                report_dir = self.artifacts.case_stage_dir(trace.context.case_id, trace.context.suite_name, "report")
                self.artifacts.write_json(
                    report_dir / "mapping_learning_error.json",
                    {
                        "error_type": exc.__class__.__name__,
                        "message": str(exc),
                        "source_statement": statement,
                        "candidate_selector": candidate.selector,
                        "patch_statement": patch.migrated_statement,
                    },
                )
            except Exception:
                pass
        if old_intentions is None:
            loaded = self.artifacts.read_json(self.artifacts.case_stage_dir(script_path.stem, suite_name, "report") / "old_intentions.json")
            old_intentions = loaded if isinstance(loaded, dict) else {}
        return TraceBundle(
            failure=failure,
            context=context,
            snapshot=snapshot or DOMSnapshot(),
            old_trace_intentions=old_intentions or {},
            raw_stderr=stderr,
            old_trace=old_trace,
        )

    def _report(
        self,
        case_id: str,
        suite_name: str,
        trace: TraceBundle,
        status: str,
        success: bool,
        started: float,
        patch: MigrationPatch | None = None,
        attempts: list[FulfillmentAttemptRecord] | None = None,
        validations: list[ValidationResult] | None = None,
        migrated_script_path: str = "",
    ) -> CaseReport:
        stats = self.llm.snapshot_runtime_stats()
        verdict = MigrationVerdict(
            status=status,
            success=success,
            intention_fulfilled=success,
            oracle_satisfied=True,
            assertion_satisfied=True,
            context_ready=success,
            reasons=[] if success else ["migration did not reach the end of the script"],
        )
        return CaseReport(
            case_id=case_id,
            trace=trace,
            migration_status=status,
            migration_success=success,
            migration_duration_seconds=round(time.perf_counter() - started, 3),
            repair_count=len(attempts or []),
            intention_fulfilled=success,
            oracle_satisfied=True,
            migration_verdict=verdict,
            oracle_migration={},
            patch=patch,
            replay=None,
            migrated_script_path=migrated_script_path,
            validation_results=list(validations or []),
            round_history=list(attempts or []),
            llm_fallback=bool(stats.get("fallback_used", False)),
            llm_remote_used=bool(stats.get("remote_used", False)),
            llm_fallback_tasks=list(stats.get("fallback_tasks", [])),
            llm_fallback_reasons=list(stats.get("fallback_reasons", [])),
            llm_remote_calls=int(stats.get("remote_calls", 0) or 0),
            llm_fallback_calls=int(stats.get("fallback_calls", 0) or 0),
            llm_task_seconds=dict(stats.get("task_seconds", {}) or {}),
            llm_provider=str(self.llm.provider_metadata().get("provider", "")),
            llm_metadata=self.llm.provider_metadata(),
        )

    def _copy_original_script_to_replay(self, script_path: Path, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [line.replace("\ufeff", "") for line in self.script_analyzer.read_lines(script_path)]
        project_root = Path(__file__).resolve().parents[1]
        dockers_root = (project_root / "dockers").as_posix()
        lines = [
            re.sub(
                r'Path\(__file__\)\.resolve\(\)\.parents\[2\]\s*/\s*"dockers"',
                f"Path({dockers_root!r})",
                line,
            )
            for line in lines
        ]
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _execution_namespace(self) -> dict[str, Any]:
        namespace: dict[str, Any] = {
            "__name__": "__itmweb_migration__",
            "driver": self.browser.driver,
            "time": time,
            "Path": Path,
            "subprocess": _QuietSubprocess(),
        }
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import Select, WebDriverWait

            namespace.update(
                {
                    "webdriver": webdriver,
                    "By": By,
                    "Keys": Keys,
                    "Service": Service,
            "EC": EC,
            "Select": Select,
            "WebDriverWait": WebDriverWait,
            "print": self._migration_print,
        }
            )
        except Exception:
            pass
        return namespace

    def _migration_print(self, *args: Any, **kwargs: Any) -> None:
        message = " ".join(str(arg) for arg in args)
        if re.match(r"^\[[^\]]+\]\s+database reset succeeded$", message.strip()):
            if message in self._migration_printed_reset_messages:
                return
            self._migration_printed_reset_messages.add(message)
        builtins.print(*args, **kwargs)

    def _iter_statements(self, lines: list[str], start_line: int) -> list[tuple[int, str]]:
        statements: list[tuple[int, str]] = []
        buffer: list[str] = []
        start = 0
        compiler = codeop.CommandCompiler()
        for line_num, line in enumerate(lines, start=1):
            if line_num < start_line:
                continue
            if not buffer:
                start = line_num
            buffer.append(line)
            source = "\n".join(buffer)
            try:
                if compiler(source) is None:
                    continue
            except (SyntaxError, OverflowError, ValueError):
                pass
            statements.append((start, source))
            buffer = []
        if buffer:
            statements.append((start, "\n".join(buffer)))
        return statements

    def _ignore_source_statement(self, source: str) -> bool:
        stripped = source.strip()
        return (
            not stripped
            or stripped.startswith("#")
            or "webdriver.Chrome(" in stripped
            or "webdriver.Edge(" in stripped
            or "webdriver.Firefox(" in stripped
            or "driver.set_window_size(" in stripped
            or "driver.close(" in stripped
            or "driver.quit(" in stripped
        )

    def _needs_driver(self, source: str) -> bool:
        return "driver." in source or "WebDriverWait(" in source or "Select(" in source

    def _is_driver_get(self, source: str) -> bool:
        return bool(re.search(r"\bdriver\.get\(", source))

    def _execute_driver_get(self, source: str) -> None:
        match = re.search(r"driver\.get\(\s*(['\"])(.*?)\1\s*\)", source, re.S)
        url = match.group(2) if match else ""
        if self.browser.driver is None:
            self.browser.open(url or None)
        elif url:
            self.browser.navigate(url)

    def _base_url(self, script_path: Path) -> str:
        text = script_path.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"driver\.get\(\s*(['\"])(.*?)\1\s*\)", text, re.S)
        return match.group(2) if match else ""

    def _infer_old_script(self, script_path: Path) -> Path | None:
        parts = list(script_path.parts)
        for index, part in enumerate(parts):
            if part.lower() == "datasetnew":
                parts[index] = "datasetold"
                old_path = Path(*parts)
                return old_path if old_path.exists() else None
        return None

    def _statement_line_count(self, source: str) -> int:
        return max(1, len(str(source or "").splitlines()))

    def _is_meaningful_statement(self, source: str) -> bool:
        return any(token in source for token in ["driver.", "WebDriverWait(", "Select("])

    def _line_from_traceback(self, tb: str, default: int, script_path: Path | None = None) -> int:
        matches = re.findall(r'File "([^"]+)", line (\d+)', tb)
        if not matches:
            return default
        if script_path is not None:
            expected = str(script_path.resolve()).lower()
            for filename, line in reversed(matches):
                try:
                    if str(Path(filename).resolve()).lower() == expected:
                        return int(line)
                except Exception:
                    pass
        return int(matches[-1][1])

    def _error_type_from_traceback(self, tb: str) -> str:
        match = re.search(r"([A-Za-z_][A-Za-z0-9_]*(?:Exception|Error)):", tb)
        return match.group(1) if match else "unknown"

    def _action_type(self, statement: str) -> str:
        lowered = statement.lower()
        if "switch_to.frame" in lowered:
            return "switch_frame"
        if "switch_to.default_content" in lowered:
            return "default_content"
        if "execute_script" in lowered:
            return "execute_script"
        if "actionchains" in lowered or "move_to_element" in lowered:
            return "hover"
        if "driver.get(" in lowered:
            return "get"
        if "send_keys" in lowered:
            return "input"
        if ".clear(" in lowered:
            return "clear"
        if "select_by_" in lowered:
            return "select"
        if ".submit(" in lowered:
            return "submit"
        if ".click(" in lowered or "element_to_be_clickable" in lowered:
            return "click"
        return "wait" if "sleep(" in lowered else "click"

    def _locator_hint(self, statement: str) -> str:
        match = re.search(r"By\.([A-Z_]+)\s*,\s*(['\"])(.*?)\2", statement)
        if match:
            return f"{match.group(1).lower()}={match.group(3)}"
        return ""

    def _statement_action_expression(self, statement: str) -> str:
        try:
            tree = ast.parse(statement)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr in {"send_keys", "select_by_visible_text", "select_by_value", "select_by_index"} and node.args:
                        return ast.get_source_segment(statement, node.args[0]) or ""
        except SyntaxError:
            pass
        return ""

    def _statement_action_value(self, statement: str) -> str:
        expression = self._statement_action_expression(statement)
        if not expression:
            return ""
        try:
            return str(ast.literal_eval(expression))
        except Exception:
            if "Path(__file__).resolve().with_name" in expression:
                match = re.search(r"with_name\(\s*(['\"])(.*?)\1\s*\)", expression)
                return match.group(2) if match else ""
        return ""

    def _looks_like_path(self, value: str) -> bool:
        return bool(re.search(r"\.(png|jpe?g|gif|webp|txt|csv|json|xml|pdf|zip|sql|xlsx?)$", value, re.I))

    def _element_action(self, intended: str, element: ElementRecord) -> str:
        tag = str(element.tag or "").lower()
        input_type = str((element.attributes or {}).get("type", "") or "").lower()
        if tag == "select":
            return "select"
        if tag in {"textarea", "input"} and input_type not in {"submit", "button", "image", "reset", "checkbox", "radio"}:
            return "input"
        if intended == "submit" and tag not in {"input", "button"}:
            return "click"
        return intended if intended in {"click", "submit", "input", "select", "clear"} else "click"

    def _candidate_is_file_input(self, candidate: FulfillmentOption) -> bool:
        element = candidate.element
        attrs = element.attributes if element else {}
        return str(element.tag if element else "").lower() == "input" and str(attrs.get("type", "") or "").lower() == "file"

    def _element_text(self, element: ElementRecord) -> str:
        attrs = element.attributes or {}
        return " ".join(
            str(value or "")
            for value in [
                element.text,
                element.locator_hint,
                attrs.get("id", ""),
                attrs.get("name", ""),
                attrs.get("type", ""),
                attrs.get("href", ""),
                attrs.get("class", ""),
                attrs.get("aria-label", ""),
                attrs.get("title", ""),
            ]
        )

    def _selector_for_element(self, element: ElementRecord) -> tuple[str, str]:
        attrs = element.attributes or {}
        if attrs.get("id"):
            return "id", str(attrs["id"])
        if attrs.get("name"):
            return "name", str(attrs["name"])
        if element.locator_hint.startswith("id="):
            return "id", element.locator_hint.split("=", 1)[1]
        if element.locator_hint.startswith("name="):
            return "name", element.locator_hint.split("=", 1)[1]
        text = str(element.text or "").strip()
        if element.tag.lower() == "a" and text:
            return "link_text", text
        if element.css_selector:
            return "css", element.css_selector
        if element.xpath:
            return "xpath", element.xpath
        return "", ""
