from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schemas import FailureInfo, FulfillmentOption, MigrationPatch, PatchType, ReplayResult
from .trace_runner import BOOTSTRAP_ACTION_LOG


class ScriptAnalyzer:
    def read_lines(self, script_path: str | Path) -> list[str]:
        return Path(script_path).read_text(encoding="utf-8", errors="ignore").splitlines()

    def get_statement(self, script_path: str | Path, line_num: int) -> str:
        lines = self.read_lines(script_path)
        return lines[line_num - 1].strip() if 1 <= line_num <= len(lines) else ""

    def get_statement_block(self, script_path: str | Path, line_num: int, max_lines: int = 80) -> str:
        lines = self.read_lines(script_path)
        if not (1 <= line_num <= len(lines)):
            return ""
        block = [lines[line_num - 1]]
        paren_balance = block[0].count("(") - block[0].count(")")
        for line in lines[line_num : line_num + max_lines - 1]:
            if paren_balance <= 0 and not block[-1].rstrip().endswith("\\"):
                break
            block.append(line)
            paren_balance += line.count("(") - line.count(")")
        return "\n".join(block).strip()

    def infer_indent(self, statement: str) -> str:
        match = re.match(r"^(\s*)", statement or "")
        return match.group(1) if match else ""

    def extract_first_url(self, script_path: str | Path) -> str:
        text = Path(script_path).read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"driver\.get\(\s*(['\"])(.*?)\1\s*\)", text, re.S)
        return match.group(2) if match else ""

    def get_context_window(self, script_path: str | Path, line_num: int, before: int = 3, after: int = 6) -> tuple[list[str], list[str]]:
        lines = self.read_lines(script_path)
        return lines[max(0, line_num - before - 1) : max(0, line_num - 1)], lines[line_num : line_num + after]

    def get_following_assertions(self, script_path: str | Path, line_num: int, max_lines: int = 80) -> list[str]:
        lines = self.read_lines(script_path)
        return [line.strip() for line in lines[line_num : line_num + max_lines] if self.is_assertion_statement(line)]

    def is_assertion_statement(self, statement: str) -> bool:
        return statement.strip().startswith("assert ") or ".assert" in statement


class PatchGenerator:
    def from_candidate(
        self,
        original_statement: str,
        line_num: int,
        candidate: FulfillmentOption,
        validation: Any | None = None,
    ) -> MigrationPatch:
        del validation
        lines = self._candidate_lines(candidate)
        return MigrationPatch(
            patch_type=PatchType.BLOCK.value,
            original_statement=original_statement,
            migrated_statement="\n".join(lines),
            line_num=line_num,
            candidate_selector=candidate.selector,
            replacement_line_count=self._statement_line_count(original_statement),
            required_imports=self._required_imports(lines),
            explanation=candidate.explanation,
        )

    def from_statement(
        self,
        original_statement: str,
        migrated_statement: str,
        line_num: int,
        explanation: str = "",
    ) -> MigrationPatch:
        return MigrationPatch(
            patch_type=PatchType.BLOCK.value,
            original_statement=original_statement,
            migrated_statement=migrated_statement,
            line_num=line_num,
            replacement_line_count=self._statement_line_count(original_statement),
            explanation=explanation,
        )

    def promote_to_flow(
        self,
        primary: MigrationPatch,
        secondary: MigrationPatch,
        explanation: str = "",
    ) -> MigrationPatch:
        return MigrationPatch(
            patch_type=PatchType.FLOW.value,
            original_statement=primary.original_statement,
            migrated_statement="\n".join([primary.migrated_statement, secondary.migrated_statement]),
            line_num=primary.line_num,
            candidate_selector=primary.candidate_selector,
            replacement_line_count=max(primary.replacement_line_count, secondary.replacement_line_count),
            required_imports=list(dict.fromkeys(primary.required_imports + secondary.required_imports)),
            explanation=explanation or primary.explanation,
        )

    def _candidate_lines(self, candidate: FulfillmentOption) -> list[str]:
        if candidate.patch_statement:
            return [candidate.patch_statement]
        recipe_steps = candidate.metadata.get("mapped_recipe_steps", [])
        if isinstance(recipe_steps, list) and recipe_steps:
            return [line for step in recipe_steps if isinstance(step, dict) for line in self._step_lines(step)]
        return self._step_lines(
            {
                "action_type": candidate.action_type,
                "selector": candidate.selector,
                "selector_type": candidate.metadata.get("selector_type", ""),
                "value_expression": candidate.metadata.get("value_expression", ""),
                "value": candidate.metadata.get("value", ""),
            }
        )

    def _step_lines(self, step: dict[str, Any]) -> list[str]:
        action = str(step.get("action_type", "") or "click").lower()
        value = str(step.get("value_expression", "") or "")
        if not value:
            value = repr(str(step.get("value", "") or ""))
        if action == "wait":
            return [f"time.sleep(float({value} or 1))"]
        if action in {"get", "open_url"}:
            return [f"driver.get({value})"]
        if action == "execute_script":
            return [f"driver.execute_script({value})"]
        if action in {"default_content", "switch_default_content"}:
            return ["driver.switch_to.default_content()"]
        if action in {"accept_alert", "alert_accept"}:
            return ["WebDriverWait(driver, 10).until(EC.alert_is_present()).accept()"]
        if action in {"dismiss_alert", "alert_dismiss"}:
            return ["WebDriverWait(driver, 10).until(EC.alert_is_present()).dismiss()"]
        locator = self._locator_expr(str(step.get("selector_type", "") or ""), str(step.get("selector", "") or ""))
        if action in {"js_click", "confirm_click"} or (
            action in {"click", "submit"} and self._is_confirmation_selector(str(step.get("selector", "") or ""))
        ):
            lines = [f"element = WebDriverWait(driver, 10).until(EC.element_to_be_clickable(({locator})))"]
            if action in {"js_click", "confirm_click"}:
                lines.append("driver.execute_script('arguments[0].click();', element)")
            else:
                lines.append("element.click()")
            return lines
        if action in {"input", "send_keys"}:
            return [
                f"element = driver.find_element({locator})",
                "element.clear() if (element.get_attribute('type') or '').lower() != 'file' else None",
                f"element.send_keys({value})",
            ]
        if action == "clear":
            return [f"driver.find_element({locator}).clear()"]
        if action == "select":
            return [f"Select(driver.find_element({locator})).select_by_visible_text({value})"]
        if action == "submit":
            return [f"driver.find_element({locator}).submit()"]
        if action in {"switch_frame", "frame"}:
            return [f"driver.switch_to.frame(driver.find_element({locator}))"]
        if action in {"hover", "move_to_element"}:
            return [f"ActionChains(driver).move_to_element(driver.find_element({locator})).perform()"]
        return [f"driver.find_element({locator}).click()"]

    def _is_confirmation_selector(self, selector: str) -> bool:
        value = str(selector or "").lower()
        return any(
            token in value
            for token in [
                "adm_messagebox_button_yes",
                "btn_yes",
                "button_yes",
                "confirm",
                "modal",
            ]
        )

    def _locator_expr(self, selector_type: str, selector: str) -> str:
        selector_type = self._selector_type(selector_type, selector)
        selector = self._selector_value(selector, selector_type)
        by_name = {
            "id": "ID",
            "name": "NAME",
            "xpath": "XPATH",
            "css": "CSS_SELECTOR",
            "link_text": "LINK_TEXT",
            "partial_link_text": "PARTIAL_LINK_TEXT",
            "class_name": "CLASS_NAME",
            "tag_name": "TAG_NAME",
        }.get(selector_type, "CSS_SELECTOR")
        return f"By.{by_name}, {selector!r}"

    def _selector_type(self, selector_type: str, selector: str) -> str:
        selector_type = selector_type.lower().strip()
        if selector_type:
            return selector_type
        for prefix, kind in [
            ("id=", "id"),
            ("name=", "name"),
            ("xpath=", "xpath"),
            ("css=", "css"),
            ("link_text=", "link_text"),
            ("partial_link_text=", "partial_link_text"),
        ]:
            if selector.startswith(prefix):
                return kind
        if selector.startswith(("/", "(")):
            return "xpath"
        return "css"

    def _selector_value(self, selector: str, selector_type: str) -> str:
        for prefix in [f"{selector_type}=", f"{selector_type}:"]:
            if selector.startswith(prefix):
                return selector.split(prefix, 1)[1]
        return selector

    def _required_imports(self, lines: list[str]) -> list[str]:
        imports = ["from selenium.webdriver.common.by import By"]
        if any("Select(" in line for line in lines):
            imports.append("from selenium.webdriver.support.ui import Select")
        if any("ActionChains(" in line for line in lines):
            imports.append("from selenium.webdriver.common.action_chains import ActionChains")
        if any("WebDriverWait(" in line or "EC." in line for line in lines):
            imports.append("from selenium.webdriver.support.ui import WebDriverWait")
            imports.append("from selenium.webdriver.support import expected_conditions as EC")
        if any("time.sleep" in line for line in lines):
            imports.append("import time")
        return imports

    def _statement_line_count(self, statement: str) -> int:
        return max(1, len(str(statement or "").splitlines()))


class PatchApplier:
    def __init__(self, script_analyzer: ScriptAnalyzer | None = None) -> None:
        self.script_analyzer = script_analyzer or ScriptAnalyzer()

    def apply_patch(self, script_path: str | Path, patch: MigrationPatch) -> Path:
        return self.apply(script_path, patch, script_path)

    def apply(self, script_path: str | Path, patch: MigrationPatch, output_path: str | Path) -> Path:
        script_path = Path(script_path)
        output_path = Path(output_path)
        lines = self.script_analyzer.read_lines(script_path)
        index = max(0, patch.line_num - 1)
        indent = self.script_analyzer.infer_indent(lines[index] if index < len(lines) else "")
        new_lines = [indent + line if line.strip() else "" for line in patch.migrated_statement.splitlines()]
        end = index + max(1, int(patch.replacement_line_count or 1))
        lines[index:end] = new_lines
        lines = self._ensure_imports(lines, patch.required_imports)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return output_path

    def _ensure_imports(self, lines: list[str], imports: list[str]) -> list[str]:
        existing = {line.strip() for line in lines}
        missing = [line for line in imports if line and line not in existing]
        if not missing:
            return lines
        index = 0
        while index < len(lines) and (lines[index].startswith("import ") or lines[index].startswith("from ")):
            index += 1
        return lines[:index] + missing + lines[index:]


@dataclass(slots=True)
class ReplayRunner:
    config: Any | None = None
    artifacts: Any | None = None

    def replay(self, script_path: str | Path) -> ReplayResult:
        script_path = Path(script_path)
        started = time.perf_counter()
        log_path = script_path.parent / "action_log.txt"
        log_path.write_text("", encoding="utf-8")
        env = self._replay_env(log_path)
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="ignore") as stdout_file:
            with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="ignore") as stderr_file:
                process = subprocess.Popen(
                    [sys.executable, str(script_path)],
                    cwd=str(script_path.parent),
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    env=env,
                )
                return_code, timed_out = self._wait_for_process_or_log_idle_timeout(process, log_path)
                if timed_out:
                    self._kill_process_tree(process.pid)
                    return_code = None
                    timeout = self._idle_timeout_seconds()
                    message = f"Replay action_log had no updates for {timeout} seconds."
                    with log_path.open("a", encoding="utf-8", errors="ignore") as handle:
                        handle.write(f"\n[stderr]\n{message}\n")
                    stdout_file.seek(0)
                    stderr_file.seek(0)
                    stdout = stdout_file.read()
                    stderr = stderr_file.read()
                    failure = FailureInfo(
                        script_path=str(script_path),
                        line_num=0,
                        broken_statement="",
                        error_type="ReplayIdleTimeout",
                        traceback=stderr,
                        message=message,
                    )
                    return ReplayResult(False, return_code, stdout, stderr, time.perf_counter() - started, failure)
                stdout_file.seek(0)
                stderr_file.seek(0)
                stdout = stdout_file.read()
                stderr = stderr_file.read()
        if return_code != 0:
            self._kill_process_tree(process.pid)
        failure = None
        if return_code != 0:
            failure = FailureInfo(
                script_path=str(script_path),
                line_num=0,
                broken_statement="",
                error_type="ReplayFailure",
                traceback=stderr,
                message="Migrated script failed during replay.",
            )
        return ReplayResult(return_code == 0, return_code, stdout, stderr, time.perf_counter() - started, failure)

    def _kill_process_tree(self, pid: int) -> None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return
        try:
            os.kill(pid, 9)
        except OSError:
            pass

    def _wait_for_process_or_log_idle_timeout(self, process: subprocess.Popen[str], log_path: Path) -> tuple[int | None, bool]:
        idle_timeout = self._idle_timeout_seconds()
        last_signature = self._log_signature(log_path)
        last_update = time.perf_counter()
        while True:
            return_code = process.poll()
            if return_code is not None:
                return return_code, False
            signature = self._log_signature(log_path)
            if signature != last_signature:
                last_signature = signature
                last_update = time.perf_counter()
            elif idle_timeout is not None and time.perf_counter() - last_update >= idle_timeout:
                return None, True
            time.sleep(0.5)

    def _log_signature(self, log_path: Path) -> tuple[int, int]:
        try:
            stat = log_path.stat()
            return int(stat.st_mtime_ns), int(stat.st_size)
        except OSError:
            return 0, 0

    def _idle_timeout_seconds(self) -> int | None:
        try:
            trace_config = getattr(self.config, "trace", None)
            value = int(
                getattr(
                    trace_config,
                    "replay_timeout_seconds",
                    getattr(trace_config, "script_timeout_seconds", 0),
                )
                or 0
            )
        except Exception:
            value = 0
        return value if value > 0 else None

    def _replay_env(self, log_path: Path) -> dict[str, str]:
        env = os.environ.copy()
        bootstrap_dir = self._ensure_bootstrap_dir()
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(bootstrap_dir) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
        browser = getattr(self.config, "browser", None)
        env["ITMWEB_TRACE_LOG_FILE"] = str(log_path)
        env["ITMWEB_TRACE_HOLD_ON_ERROR"] = "0"
        env["ITMWEB_CLOSE_BROWSER_ON_ERROR"] = "1"
        env["ITMWEB_BROWSER_NO_PROXY_SERVER"] = "1" if getattr(browser, "force_no_proxy_server", True) else "0"
        env["ITMWEB_BROWSER_ISOLATED_PROFILE"] = "1" if getattr(browser, "use_isolated_user_data_dir", True) else "0"
        env["ITMWEB_BROWSER_ISOLATED_PROFILE_ROOT"] = str(
            getattr(browser, "isolated_user_data_root", "") or ""
        )
        return env

    def _ensure_bootstrap_dir(self) -> Path:
        if self.artifacts is not None:
            trace_config = getattr(self.config, "trace", None)
            name = str(getattr(trace_config, "bootstrap_dir_name", "") or ".itmweb_bootstrap")
            bootstrap_dir = self.artifacts.bootstrap_dir(name)
        else:
            bootstrap_dir = Path(os.environ.get("TEMP", ".")) / "itmweb_replay_bootstrap"
            bootstrap_dir.mkdir(parents=True, exist_ok=True)
        (bootstrap_dir / "sitecustomize.py").write_text(BOOTSTRAP_ACTION_LOG, encoding="utf-8")
        return bootstrap_dir
