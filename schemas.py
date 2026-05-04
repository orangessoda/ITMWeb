from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BrowserType(str, Enum):
    CHROME = "chrome"
    EDGE = "edge"
    FIREFOX = "firefox"


class FailureType(str, Enum):
    UNKNOWN = "unknown"
    NO_SUCH_ELEMENT = "NoSuchElement"
    TIMEOUT = "Timeout"
    STALE_ELEMENT = "StaleElementReference"
    ELEMENT_NOT_INTERACTABLE = "ElementNotInteractable"
    ELEMENT_CLICK_INTERCEPTED = "ElementClickIntercepted"


class ActionType(str, Enum):
    NAVIGATION = "navigation"
    CLICK = "click"
    JS_CLICK = "js_click"
    INPUT = "input"
    CLEAR = "clear"
    SELECT = "select"
    SUBMIT = "submit"
    PRESS_ENTER = "press_enter"
    WAIT = "wait"
    HOVER = "hover"
    SCROLL_INTO_VIEW = "scroll_into_view"
    EXECUTE_SCRIPT = "execute_script"
    SWITCH_FRAME = "switch_frame"
    SWITCH_WINDOW = "switch_window"
    ACCEPT_ALERT = "accept_alert"
    DISMISS_ALERT = "dismiss_alert"


class ValidationVerdict(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class PatchType(str, Enum):
    STATEMENT = "statement"
    BLOCK = "block"
    FLOW = "flow"


@dataclass(slots=True)
class FailureInfo:
    script_path: str
    line_num: int
    broken_statement: str
    error_type: str = FailureType.UNKNOWN.value
    traceback: str = ""
    message: str = ""
    detected_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScriptContext:
    script_path: str
    case_id: str
    suite_name: str = ""
    base_url: str = ""
    previous_steps: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ElementRecord:
    index: int
    tag: str
    locator_hint: str = ""
    text: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    is_visible: bool = True
    is_enabled: bool = True
    xpath: str = ""
    css_selector: str = ""
    bounding_box: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DOMSnapshot:
    url: str = ""
    title: str = ""
    html: str = ""
    dom_excerpt: str = ""
    screenshot_path: str = ""
    page_source_path: str = ""
    interactables: list[ElementRecord] = field(default_factory=list)
    captured_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "html": self.html,
            "dom_excerpt": self.dom_excerpt,
            "screenshot_path": self.screenshot_path,
            "page_source_path": self.page_source_path,
            "interactables": [item.to_dict() for item in self.interactables],
            "captured_at": self.captured_at,
        }


@dataclass(slots=True)
class ActionRecord:
    action_type: str
    target: str = ""
    value: str = ""
    reasoning: str = ""
    success: bool = False
    started_at: str = field(default_factory=utc_now)
    finished_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TraceAction:
    stage: str
    action: str
    detail: str = ""
    note: str = ""
    index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TraceRun:
    label: str
    environment: str
    script_path: str
    status: str
    success: bool = False
    return_code: int | None = None
    duration_seconds: float = 0.0
    log_path: str = ""
    stdout_path: str = ""
    stderr_path: str = ""
    stdout_tail: str = ""
    stderr_tail: str = ""
    error_type: str = ""
    failure_message: str = ""
    actions: list[TraceAction] = field(default_factory=list)
    recorded_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "actions": [item.to_dict() for item in self.actions],
        }


@dataclass(slots=True)
class TraceBundle:
    failure: FailureInfo
    context: ScriptContext
    snapshot: DOMSnapshot
    action_history: list[ActionRecord] = field(default_factory=list)
    old_trace_intentions: dict[str, Any] = field(default_factory=dict)
    raw_stdout: str = ""
    raw_stderr: str = ""
    old_trace: TraceRun | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure": self.failure.to_dict(),
            "context": self.context.to_dict(),
            "snapshot": self.snapshot.to_dict(),
            "action_history": [item.to_dict() for item in self.action_history],
            "old_trace_intentions": dict(self.old_trace_intentions),
            "raw_stdout": self.raw_stdout,
            "raw_stderr": self.raw_stderr,
            "old_trace": self.old_trace.to_dict() if self.old_trace else None,
        }


@dataclass(slots=True)
class IntentRecord:
    name: str
    description: str
    action_type: str
    target_semantics: str = ""
    constraints: list[str] = field(default_factory=list)
    expected_outcome: str = ""
    confidence: float = 0.0
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FulfillmentOption:
    source: str
    action_type: str
    selector: str
    element: ElementRecord | None = None
    confidence: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    explanation: str = ""
    patch_statement: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "element": self.element.to_dict() if self.element else None,
        }


@dataclass(slots=True)
class ValidationResult:
    verdict: str
    candidate_selector: str = ""
    passed_checks: list[str] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MigrationPatch:
    patch_type: str
    original_statement: str
    migrated_statement: str
    line_num: int
    candidate_selector: str = ""
    replacement_line_count: int = 1
    required_imports: list[str] = field(default_factory=list)
    inserted_lines_before: list[str] = field(default_factory=list)
    inserted_lines_after: list[str] = field(default_factory=list)
    flow_patch_kind: str = ""
    flow_patch_steps: list[str] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReplayResult:
    success: bool
    return_code: int | None
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    failure: FailureInfo | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "return_code": self.return_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": self.duration_seconds,
            "failure": self.failure.to_dict() if self.failure else None,
        }


@dataclass(slots=True)
class FulfillmentAttemptRecord:
    round_index: int
    intention_step_index: int = 0
    candidate_id: str = ""
    selector: str = ""
    action_type: str = ""
    verdict: str = ""
    plan_source: str = ""
    failed_checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MigrationVerdict:
    status: str = "blocked"
    success: bool = False
    intention_fulfilled: bool = False
    oracle_satisfied: bool = False
    assertion_satisfied: bool = True
    context_ready: bool = False
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CaseReport:
    case_id: str
    trace: TraceBundle
    migration_status: str = "blocked"
    migration_success: bool = False
    migration_duration_seconds: float = 0.0
    repair_count: int = 0
    intention_fulfilled: bool = False
    oracle_satisfied: bool = False
    migration_verdict: MigrationVerdict | None = None
    oracle_migration: dict[str, Any] = field(default_factory=dict)
    patch: MigrationPatch | None = None
    replay: ReplayResult | None = None
    migrated_script_path: str = ""
    validation_results: list[ValidationResult] = field(default_factory=list)
    round_history: list[FulfillmentAttemptRecord] = field(default_factory=list)
    llm_fallback: bool = False
    llm_remote_used: bool = False
    llm_fallback_tasks: list[str] = field(default_factory=list)
    llm_fallback_reasons: list[str] = field(default_factory=list)
    llm_remote_calls: int = 0
    llm_fallback_calls: int = 0
    llm_task_seconds: dict[str, float] = field(default_factory=dict)
    llm_provider: str = ""
    llm_metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "trace": self.trace.to_dict(),
            "migration_status": self.migration_status,
            "migration_success": self.migration_success,
            "migration_duration_seconds": self.migration_duration_seconds,
            "repair_count": self.repair_count,
            "migration_verdict": self.migration_verdict.to_dict() if self.migration_verdict else None,
            "oracle_migration": dict(self.oracle_migration),
            "migrated_script_path": self.migrated_script_path,
            "patch": self.patch.to_dict() if self.patch else None,
            "replay": self.replay.to_dict() if self.replay else None,
            "validation_results": [item.to_dict() for item in self.validation_results],
            "round_history": [item.to_dict() for item in self.round_history],
            "llm_remote_used": self.llm_remote_used,
            "llm_remote_calls": self.llm_remote_calls,
            "llm_task_seconds": dict(self.llm_task_seconds),
            "llm_provider": self.llm_provider,
            "llm_metadata": dict(self.llm_metadata),
            "created_at": self.created_at,
        }
