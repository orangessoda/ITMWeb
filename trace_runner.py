from __future__ import annotations

import os
import json
import re
import subprocess
import sys
import threading
import time
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .report import ArtifactManager
from .schemas import TraceAction, TraceRun


@dataclass(slots=True)
class TraceRunResult:
    trace: TraceRun
    stdout: str
    stderr: str


@dataclass(slots=True)
class ExistingTraceArtifacts:
    old_capture: TraceRunResult | None = None
    loaded_from_artifacts: bool = False


class TraceArtifactLoader:
    def __init__(self, artifacts: ArtifactManager) -> None:
        self.artifacts = artifacts

    def load_existing_trace_artifacts(self, case_id: str, suite_name: str) -> ExistingTraceArtifacts:
        trace_dir = self.artifacts.case_stage_dir(case_id, suite_name, "trace")
        artifacts = ExistingTraceArtifacts(
            old_capture=self.load_trace_run_result_from_action_log(
                trace_dir / "action_log.txt",
                label="old_trace",
                environment="old",
            )
        )
        report_payload = self.read_json_dict(self.artifacts.case_stage_dir(case_id, suite_name, "report") / "case_report.json") or {}
        trace_payload = report_payload.get("trace", {}) if isinstance(report_payload.get("trace"), dict) else {}
        if trace_payload:
            artifacts.old_capture = self.merge_trace_run_result(
                artifacts.old_capture,
                self.trace_run_result_from_payload(trace_payload.get("old_trace")),
            )
        artifacts.loaded_from_artifacts = artifacts.old_capture is not None
        return artifacts

    def merge_trace_run_result(
        self,
        action_log_result: TraceRunResult | None,
        report_result: TraceRunResult | None,
    ) -> TraceRunResult | None:
        if action_log_result is None:
            return report_result
        if report_result is None:
            return action_log_result
        trace = action_log_result.trace
        report_trace = report_result.trace
        if report_trace.duration_seconds:
            trace.duration_seconds = report_trace.duration_seconds
        if report_trace.script_path:
            trace.script_path = report_trace.script_path
        if report_trace.status:
            trace.status = report_trace.status
        trace.success = report_trace.success
        if report_trace.return_code is not None:
            trace.return_code = report_trace.return_code
        if report_trace.failure_message and not trace.failure_message:
            trace.failure_message = report_trace.failure_message
        return action_log_result

    def read_json_dict(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def read_text_if_exists(self, path: str) -> str:
        if not path:
            return ""
        target = Path(path)
        if not target.exists():
            return ""
        try:
            return target.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def load_trace_run_result_from_action_log(
        self,
        log_path: Path,
        label: str,
        environment: str,
    ) -> TraceRunResult | None:
        if not log_path.exists():
            return None
        try:
            text = log_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None
        action_text = text.split("[stdout]", 1)[0]
        stdout = ""
        stderr = ""
        if "[stdout]" in text:
            after_stdout = text.split("[stdout]", 1)[1]
            stdout, stderr = after_stdout.split("[stderr]", 1) if "[stderr]" in after_stdout else (after_stdout, "")
        actions: list[TraceAction] = []
        last_action: TraceAction | None = None
        action_pattern = re.compile(
            r"^\[ACTION\]\[(?P<stage>[A-Z]+)\]\s+(?P<action>\S+)\s*(?P<rest>.*?)(?:\s+\|\s+note:\s*(?P<note>.*))?$"
        )
        for index, line in enumerate(action_text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("[PAGE_STATE] "):
                if last_action is not None:
                    try:
                        state = json.loads(stripped[len("[PAGE_STATE] ") :])
                    except json.JSONDecodeError:
                        state = None
                    if isinstance(state, dict):
                        states = last_action.metadata.setdefault("page_states", [])
                        if isinstance(states, list):
                            states.append(state)
                continue
            match = action_pattern.match(stripped)
            if not match:
                continue
            last_action = TraceAction(
                stage=str(match.group("stage") or ""),
                action=str(match.group("action") or ""),
                detail=str(match.group("rest") or "").strip(),
                note=str(match.group("note") or "").strip(),
                index=index,
            )
            actions.append(last_action)
        if not actions:
            return None
        failed = next((item for item in actions if item.stage.upper() == "FAIL"), None)
        trace = TraceRun(
            label=label,
            environment=environment,
            script_path="",
            status="failed" if failed else "passed",
            success=failed is None,
            return_code=1 if failed else 0,
            log_path=str(log_path),
            stdout_tail=stdout[-4000:],
            stderr_tail=stderr[-4000:],
            error_type="TraceActionFailure" if failed else "",
            failure_message=failed.detail if failed else "",
            actions=actions,
            metadata={"loaded_from_action_log": True},
        )
        return TraceRunResult(trace=trace, stdout=stdout, stderr=stderr)

    def trace_run_result_from_payload(self, payload: Any) -> TraceRunResult | None:
        if not isinstance(payload, dict):
            return None
        trace = TraceRun(
            label=str(payload.get("label", "") or ""),
            environment=str(payload.get("environment", "") or ""),
            script_path=str(payload.get("script_path", "") or ""),
            status=str(payload.get("status", "") or ""),
            success=bool(payload.get("success", False)),
            return_code=payload.get("return_code"),
            duration_seconds=float(payload.get("duration_seconds", 0.0) or 0.0),
            log_path=str(payload.get("log_path", "") or ""),
            stdout_path=str(payload.get("stdout_path", "") or ""),
            stderr_path=str(payload.get("stderr_path", "") or ""),
            stdout_tail=str(payload.get("stdout_tail", "") or ""),
            stderr_tail=str(payload.get("stderr_tail", "") or ""),
            error_type=str(payload.get("error_type", "") or ""),
            failure_message=str(payload.get("failure_message", "") or ""),
            actions=[
                TraceAction(
                    stage=str(item.get("stage", "") or ""),
                    action=str(item.get("action", "") or ""),
                    detail=str(item.get("detail", "") or ""),
                    note=str(item.get("note", "") or ""),
                    index=int(item.get("index", 0) or 0),
                    metadata=item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {},
                )
                for item in payload.get("actions", [])
                if isinstance(item, dict)
            ],
            recorded_at=str(payload.get("recorded_at", "") or ""),
            metadata=payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {},
        )
        stdout = self.read_text_if_exists(trace.stdout_path) or trace.stdout_tail
        stderr = self.read_text_if_exists(trace.stderr_path) or trace.stderr_tail
        return TraceRunResult(trace=trace, stdout=stdout, stderr=stderr)


BOOTSTRAP_ACTION_LOG = textwrap.dedent(
    """
    import json
    import os
    import shutil
    import sys
    import tempfile
    import time
    import traceback
    import atexit

    def _trace_env(name, default=""):
        value = os.environ.get(name)
        if value is None:
            return default
        value = str(value).strip()
        return value if value else default

    def _safe_print(message):
        try:
            print(message, flush=True)
        except Exception:
            pass
        try:
            path = _trace_env("ITMWEB_TRACE_LOG_FILE", "")
            if path:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "a", encoding="utf-8", errors="ignore") as handle:
                    handle.write(str(message) + "\\n")
        except Exception:
            pass

    def _log(stage, action, detail, note):
        _safe_print(f"[ACTION][{stage}] {action} {detail} | note: {note}")

    _trace_force_no_proxy = _trace_env("ITMWEB_BROWSER_NO_PROXY_SERVER", "1") != "0"
    _trace_use_isolated_profile = _trace_env("ITMWEB_BROWSER_ISOLATED_PROFILE", "1") != "0"
    _trace_isolated_profile_root = _trace_env("ITMWEB_BROWSER_ISOLATED_PROFILE_ROOT", "")
    _trace_created_profile_dirs = []

    def _cleanup_trace_profiles():
        for profile_dir in list(_trace_created_profile_dirs):
            try:
                if profile_dir and os.path.isdir(profile_dir):
                    shutil.rmtree(profile_dir, ignore_errors=True)
            except Exception:
                pass

    atexit.register(_cleanup_trace_profiles)

    def _chrome_option_args(options):
        try:
            return list(getattr(options, "arguments", []) or [])
        except Exception:
            return []

    def _ensure_trace_chrome_options(options):
        try:
            from selenium.webdriver.chrome.options import Options as ChromeOptions
        except Exception:
            return options
        if options is None:
            options = ChromeOptions()
        args = _chrome_option_args(options)
        if _trace_force_no_proxy and "--no-proxy-server" not in args:
            options.add_argument("--no-proxy-server")
        if _trace_force_no_proxy and not any(arg.startswith("--proxy-bypass-list=") for arg in args):
            options.add_argument("--proxy-bypass-list=*.local;localhost;127.0.0.1")
        if _trace_use_isolated_profile and not any(arg.startswith("--user-data-dir=") for arg in args):
            profile_root = _trace_isolated_profile_root or os.path.join(tempfile.gettempdir(), "itmweb_trace_profiles")
            os.makedirs(profile_root, exist_ok=True)
            profile_dir = tempfile.mkdtemp(prefix="chrome_profile_", dir=profile_root)
            _trace_created_profile_dirs.append(profile_dir)
            options.add_argument(f"--user-data-dir={profile_dir}")
        return options

    _trace_action_index = 0

    def _capture_page_state(driver, trigger, note):
        if driver is None:
            return
        try:
            executor = getattr(driver, "_itmweb_original_execute_script", None)
            if executor is None:
                return
            state = executor(
                '''
                const nodes = Array.from(document.querySelectorAll(
                  'a,button,input,select,textarea,[role="button"],[onclick]'
                )).slice(0, 50);
                const visibleText = (el) => {
                  const text = (el.innerText || el.value || el.getAttribute('aria-label') ||
                    el.getAttribute('title') || el.getAttribute('placeholder') || '').trim();
                  return text.replace(/\\s+/g, ' ').slice(0, 140);
                };
                const boxOf = (el) => {
                  const r = el.getBoundingClientRect();
                  return {x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height)};
                };
                return {
                  url: location.href,
                  title: document.title,
                  widgets: nodes.map((el, index) => ({
                    index: index + 1,
                    tag: (el.tagName || '').toLowerCase(),
                    text: visibleText(el),
                    id: el.id || '',
                    name: el.getAttribute('name') || '',
                    type: el.getAttribute('type') || '',
                    role: el.getAttribute('role') || '',
                    href: el.getAttribute('href') || '',
                    enabled: !el.disabled,
                    visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                    box: boxOf(el)
                  }))
                };
                '''
            )
            payload = {
                "action_index": _trace_action_index,
                "trigger": str(trigger),
                "note": str(note)[:200],
                "url": str((state or {}).get("url", ""))[:300],
                "title": str((state or {}).get("title", ""))[:200],
                "widgets": (state or {}).get("widgets", [])[:50],
            }
            _safe_print("[PAGE_STATE] " + json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass

    _hold_on_error = _trace_env("ITMWEB_TRACE_HOLD_ON_ERROR", "0") == "1"
    try:
        _hold_seconds = int(float(_trace_env("ITMWEB_TRACE_HOLD_SECONDS", "600")))
    except Exception:
        _hold_seconds = 600
    if _hold_seconds < 1:
        _hold_seconds = 1

    def _stop_trace_on_error(exc):
        try:
            tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            _safe_print("[stderr]")
            _safe_print(tb_text.rstrip("\\n"))
        except Exception:
            pass
        os._exit(1)

    if _hold_on_error:
        def _hold_excepthook(exc_type, exc, tb):
            _safe_print("[stderr]")
            try:
                tb_text = "".join(traceback.format_exception(exc_type, exc, tb))
                _safe_print(tb_text.rstrip("\\n"))
            except Exception:
                traceback.print_exception(exc_type, exc, tb)
            _safe_print(f"[ACTION][HOLD] exception hold_seconds={_hold_seconds} | note: browser kept open for debugging")
            end_at = time.time() + _hold_seconds
            while time.time() < end_at:
                time.sleep(1)
        sys.excepthook = _hold_excepthook

    def _format_locator(element):
        locator = getattr(element, "_itmweb_trace_locator", None)
        if not locator:
            return "unknown"
        by, value = locator
        return f"{by}={value}"

    try:
        from selenium.webdriver.remote.webdriver import WebDriver as RemoteWebDriver
        from selenium.webdriver.remote.webelement import WebElement as RemoteWebElement
        from selenium.webdriver.remote.switch_to import SwitchTo as RemoteSwitchTo
        from selenium.webdriver.common.action_chains import ActionChains as SeleniumActionChains
        from selenium import webdriver as SeleniumWebDriver
    except Exception:
        RemoteWebDriver = None
        RemoteWebElement = None
        RemoteSwitchTo = None
        SeleniumActionChains = None
        SeleniumWebDriver = None

    if SeleniumWebDriver is not None and hasattr(SeleniumWebDriver, "Chrome"):
        _orig_chrome_ctor = SeleniumWebDriver.Chrome

        def _chrome_ctor_with_trace_options(*args, **kwargs):
            kwargs["options"] = _ensure_trace_chrome_options(kwargs.get("options"))
            return _orig_chrome_ctor(*args, **kwargs)

        SeleniumWebDriver.Chrome = _chrome_ctor_with_trace_options

    if RemoteWebDriver is not None and RemoteWebElement is not None:
        _orig_get = RemoteWebDriver.get
        _orig_find = RemoteWebDriver.find_element
        _orig_execute_script = RemoteWebDriver.execute_script
        RemoteWebDriver._itmweb_original_execute_script = _orig_execute_script
        _orig_click = RemoteWebElement.click
        _orig_send_keys = RemoteWebElement.send_keys
        _orig_clear = RemoteWebElement.clear
        _orig_submit = RemoteWebElement.submit

        def _get_with_log(self, url):
            global _trace_action_index
            _trace_action_index += 1
            _log("TRY", "get", f"url={url}", "opening page")
            try:
                result = _orig_get(self, url)
                _log("OK", "get", f"url={url}", "page opened")
                _capture_page_state(self, "after_get", f"url={url}")
                return result
            except Exception as exc:
                _log("FAIL", "get", f"url={url} error={exc}", "page open failed")
                _capture_page_state(self, "failed_get", f"url={url}")
                _stop_trace_on_error(exc)

        def _find_with_log(self, by=None, value=None):
            global _trace_action_index
            _trace_action_index += 1
            _log("TRY", "find_element", f"by={by} value={value}", "locating element")
            try:
                element = _orig_find(self, by, value)
                try:
                    element._itmweb_trace_locator = (by, value)
                except Exception:
                    pass
                _log("OK", "find_element", f"by={by} value={value}", "element located")
                return element
            except Exception as exc:
                _log("FAIL", "find_element", f"by={by} value={value} error={exc}", "element lookup failed")
                _capture_page_state(self, "failed_find_element", f"by={by} value={value}")
                _stop_trace_on_error(exc)

        def _click_with_log(self):
            global _trace_action_index
            locator = _format_locator(self)
            _trace_action_index += 1
            _log("TRY", "click", f"locator={locator}", "clicking element")
            try:
                result = _orig_click(self)
                _log("OK", "click", f"locator={locator}", "click succeeded")
                _capture_page_state(getattr(self, "_parent", None), "after_click", f"locator={locator}")
                return result
            except Exception as exc:
                _log("FAIL", "click", f"locator={locator} error={exc}", "click failed")
                _capture_page_state(getattr(self, "_parent", None), "failed_click", f"locator={locator}")
                _stop_trace_on_error(exc)

        def _send_keys_with_log(self, *value):
            global _trace_action_index
            locator = _format_locator(self)
            _trace_action_index += 1
            payload = "".join(str(item) for item in value)
            _log("TRY", "send_keys", f"locator={locator} text={json.dumps(payload)}", "typing into element")
            try:
                result = _orig_send_keys(self, *value)
                _log("OK", "send_keys", f"locator={locator}", "typing succeeded")
                return result
            except Exception as exc:
                _log("FAIL", "send_keys", f"locator={locator} error={exc}", "typing failed")
                _stop_trace_on_error(exc)

        def _clear_with_log(self):
            global _trace_action_index
            locator = _format_locator(self)
            _trace_action_index += 1
            _log("TRY", "clear", f"locator={locator}", "clearing element")
            try:
                result = _orig_clear(self)
                _log("OK", "clear", f"locator={locator}", "clear succeeded")
                return result
            except Exception as exc:
                _log("FAIL", "clear", f"locator={locator} error={exc}", "clear failed")
                _stop_trace_on_error(exc)

        def _submit_with_log(self):
            global _trace_action_index
            locator = _format_locator(self)
            _trace_action_index += 1
            _log("TRY", "submit", f"locator={locator}", "submitting element")
            try:
                result = _orig_submit(self)
                _log("OK", "submit", f"locator={locator}", "submit succeeded")
                _capture_page_state(getattr(self, "_parent", None), "after_submit", f"locator={locator}")
                return result
            except Exception as exc:
                _log("FAIL", "submit", f"locator={locator} error={exc}", "submit failed")
                _capture_page_state(getattr(self, "_parent", None), "failed_submit", f"locator={locator}")
                _stop_trace_on_error(exc)

        def _execute_script_with_log(self, script, *args):
            global _trace_action_index
            _trace_action_index += 1
            snippet = " ".join(str(script).split())[:160]
            _log("TRY", "execute_script", f"script={json.dumps(snippet)}", "executing javascript")
            try:
                result = _orig_execute_script(self, script, *args)
                _log("OK", "execute_script", f"script={json.dumps(snippet)}", "javascript executed")
                _capture_page_state(self, "after_execute_script", f"script={snippet}")
                return result
            except Exception as exc:
                _log("FAIL", "execute_script", f"script={json.dumps(snippet)} error={exc}", "javascript execution failed")
                _capture_page_state(self, "failed_execute_script", f"script={snippet}")
                _stop_trace_on_error(exc)

        RemoteWebDriver.get = _get_with_log
        RemoteWebDriver.find_element = _find_with_log
        RemoteWebDriver.execute_script = _execute_script_with_log
        RemoteWebElement.click = _click_with_log
        RemoteWebElement.send_keys = _send_keys_with_log
        RemoteWebElement.clear = _clear_with_log
        RemoteWebElement.submit = _submit_with_log
    if RemoteSwitchTo is not None:
        _orig_switch_window = RemoteSwitchTo.window
        _orig_switch_frame = RemoteSwitchTo.frame

        def _window_with_log(self, window_name):
            global _trace_action_index
            _trace_action_index += 1
            driver = getattr(self, "_driver", None)
            _log("TRY", "switch_window", f"value={window_name}", "switching browser window")
            try:
                result = _orig_switch_window(self, window_name)
                _log("OK", "switch_window", f"value={window_name}", "window switched")
                _capture_page_state(driver, "after_switch_window", f"value={window_name}")
                return result
            except Exception as exc:
                _log("FAIL", "switch_window", f"value={window_name} error={exc}", "window switch failed")
                _capture_page_state(driver, "failed_switch_window", f"value={window_name}")
                _stop_trace_on_error(exc)

        def _frame_with_log(self, frame_reference):
            global _trace_action_index
            _trace_action_index += 1
            driver = getattr(self, "_driver", None)
            detail = _format_locator(frame_reference) if hasattr(frame_reference, "_parent") else str(frame_reference)
            _log("TRY", "switch_frame", f"locator={detail}", "switching frame")
            try:
                result = _orig_switch_frame(self, frame_reference)
                _log("OK", "switch_frame", f"locator={detail}", "frame switched")
                _capture_page_state(driver, "after_switch_frame", f"locator={detail}")
                return result
            except Exception as exc:
                _log("FAIL", "switch_frame", f"locator={detail} error={exc}", "frame switch failed")
                _capture_page_state(driver, "failed_switch_frame", f"locator={detail}")
                _stop_trace_on_error(exc)

        RemoteSwitchTo.window = _window_with_log
        RemoteSwitchTo.frame = _frame_with_log
    if SeleniumActionChains is not None:
        _orig_move_to_element = SeleniumActionChains.move_to_element
        _orig_perform = SeleniumActionChains.perform

        def _move_to_element_with_log(self, to_element):
            try:
                self._itmweb_hover_target = _format_locator(to_element)
            except Exception:
                self._itmweb_hover_target = "unknown"
            return _orig_move_to_element(self, to_element)

        def _perform_with_log(self):
            global _trace_action_index
            _trace_action_index += 1
            driver = getattr(self, "_driver", None)
            locator = getattr(self, "_itmweb_hover_target", "unknown")
            _log("TRY", "hover", f"locator={locator}", "performing action chain")
            try:
                result = _orig_perform(self)
                _log("OK", "hover", f"locator={locator}", "action chain performed")
                _capture_page_state(driver, "after_hover", f"locator={locator}")
                return result
            except Exception as exc:
                _log("FAIL", "hover", f"locator={locator} error={exc}", "action chain failed")
                _capture_page_state(driver, "failed_hover", f"locator={locator}")
                _stop_trace_on_error(exc)

        SeleniumActionChains.move_to_element = _move_to_element_with_log
        SeleniumActionChains.perform = _perform_with_log
    """
).strip() + "\n"



@dataclass(slots=True)
class InstrumentedScriptRunner:
    config: ProjectConfig
    artifacts: ArtifactManager
    bootstrap_action_log: str = BOOTSTRAP_ACTION_LOG

    def run(
        self,
        script_path: Path,
        artifact_dir: Path,
        label: str,
        environment: str,
    ) -> TraceRunResult:
        script_path = script_path.resolve()
        trace_dir = artifact_dir / "trace"
        trace_dir.mkdir(parents=True, exist_ok=True)
        log_path = trace_dir / "action_log.txt"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.open("w", encoding="utf-8").close()
        bootstrap_dir = self._ensure_bootstrap_dir()
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(bootstrap_dir) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
        env["ITMWEB_TRACE_LOG_FILE"] = str(log_path)
        env["ITMWEB_TRACE_HOLD_ON_ERROR"] = "0"
        env["ITMWEB_TRACE_HOLD_SECONDS"] = str(max(1, self.config.trace.hold_seconds_on_failure))
        env["ITMWEB_BROWSER_NO_PROXY_SERVER"] = "1" if self.config.browser.force_no_proxy_server else "0"
        env["ITMWEB_BROWSER_ISOLATED_PROFILE"] = "1" if self.config.browser.use_isolated_user_data_dir else "0"
        env["ITMWEB_BROWSER_ISOLATED_PROFILE_ROOT"] = str(self.config.browser.isolated_user_data_root)

        started = time.perf_counter()
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        process: subprocess.Popen[str] | None = None
        stdout_thread: threading.Thread | None = None
        stderr_thread: threading.Thread | None = None
        try:
            process = subprocess.Popen(
                [sys.executable, str(script_path)],
                cwd=str(script_path.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                bufsize=1,
            )

            stdout_thread = threading.Thread(
                target=self._stream_pipe_to_action_log,
                args=(process.stdout, log_path, stdout_parts, "stdout"),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=self._stream_pipe_to_action_log,
                args=(process.stderr, log_path, stderr_parts, "stderr"),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            return_code = process.wait(timeout=self.config.trace.script_timeout_seconds)
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
            status = "passed" if return_code == 0 else "failed"
        except subprocess.TimeoutExpired:
            if process is not None:
                process.kill()
            if stdout_thread is not None:
                stdout_thread.join(timeout=5)
            if stderr_thread is not None:
                stderr_thread.join(timeout=5)
            return_code = None
            status = "timeout"
        except Exception as exc:
            stderr_parts.append(str(exc))
            with log_path.open("a", encoding="utf-8", errors="ignore") as handle:
                handle.write("\n[stderr]\n")
                handle.write(str(exc))
                handle.write("\n")
                handle.flush()
            return_code = None
            status = "error"
        duration = round(time.perf_counter() - started, 3)

        stdout = "".join(stdout_parts)
        stderr = "".join(stderr_parts)
        combined_log = self._compose_log(log_path, stdout, stderr)
        actions = self._parse_actions(combined_log)
        trace_run = TraceRun(
            label=label,
            environment=environment,
            script_path=str(script_path),
            status=status,
            success=status == "passed",
            return_code=return_code,
            duration_seconds=duration,
            log_path=str(log_path),
            stdout_path="",
            stderr_path="",
            stdout_tail=stdout[-self.config.trace.stdout_tail_chars :],
            stderr_tail=stderr[-self.config.trace.stderr_tail_chars :],
            error_type=self._extract_error_type(stderr, status),
            failure_message=self._extract_failure_message(stderr, status),
            actions=actions,
            metadata={},
        )
        return TraceRunResult(trace=trace_run, stdout=stdout, stderr=stderr)

    @staticmethod
    def _stream_pipe_to_action_log(pipe: Any, log_path: Path, chunks: list[str], section: str) -> None:
        if pipe is None:
            return
        section_written = False
        with log_path.open("a", encoding="utf-8", errors="ignore") as handle:
            while True:
                chunk = pipe.readline()
                if chunk == "":
                    break
                chunks.append(chunk)
                if section == "stdout" and (
                    chunk.startswith("[ACTION]")
                    or chunk.startswith("[PAGE_STATE]")
                    or chunk.startswith("[stderr]")
                ):
                    continue
                if not section_written:
                    handle.write(f"\n[{section}]\n")
                    section_written = True
                handle.write(chunk)
                handle.flush()
        try:
            pipe.close()
        except Exception:
            pass

    def _ensure_bootstrap_dir(self) -> Path:
        bootstrap_dir = self.artifacts.bootstrap_dir(self.config.trace.bootstrap_dir_name)
        (bootstrap_dir / "sitecustomize.py").write_text(self.bootstrap_action_log, encoding="utf-8")
        return bootstrap_dir

    def _compose_log(self, log_path: Path, stdout: str, stderr: str) -> str:
        early = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
        return (
            f"{early}\n"
            "[stdout]\n"
            f"{stdout}\n\n"
            "[stderr]\n"
            f"{stderr}\n"
        ).strip() + "\n"

    def _parse_actions(self, text: str) -> list[TraceAction]:
        pattern = re.compile(r"^\[ACTION\]\[(?P<stage>[^\]]+)\]\s+(?P<action>\S+)\s*(?P<detail>.*?)\s+\|\s+note:\s*(?P<note>.*)$")
        actions: list[TraceAction] = []
        last_action: TraceAction | None = None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("[PAGE_STATE] "):
                if last_action is not None:
                    try:
                        state = json.loads(stripped[len("[PAGE_STATE] ") :])
                    except json.JSONDecodeError:
                        state = None
                    if isinstance(state, dict):
                        states = last_action.metadata.setdefault("page_states", [])
                        if isinstance(states, list):
                            states.append(state)
                continue
            match = pattern.match(stripped)
            if not match:
                continue
            last_action = TraceAction(
                stage=match.group("stage"),
                action=match.group("action"),
                detail=match.group("detail").strip(),
                note=match.group("note").strip(),
                index=len(actions) + 1,
            )
            actions.append(last_action)
        return actions

    def _extract_error_type(self, stderr: str, status: str) -> str:
        if status == "timeout":
            return "TimeoutExpired"
        match = re.search(r"([A-Za-z_][A-Za-z0-9_]*Exception|AssertionError|Error):", stderr)
        if match:
            return match.group(1)
        return "RuntimeError" if status == "error" else ""

    def _extract_failure_message(self, stderr: str, status: str) -> str:
        stripped = [line.strip() for line in stderr.splitlines() if line.strip()]
        if stripped:
            return stripped[-1][:500]
        if status == "timeout":
            return "Script execution timed out during trace collection."
        if status == "error":
            return "Script execution crashed before completion."
        return ""
