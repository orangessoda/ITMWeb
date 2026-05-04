from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schemas import FailureInfo, FulfillmentOption, MigrationPatch, PatchType, ReplayResult


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
        locator = self._locator_expr(str(step.get("selector_type", "") or ""), str(step.get("selector", "") or ""))
        value = str(step.get("value_expression", "") or "")
        if not value:
            value = repr(str(step.get("value", "") or ""))
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
        if action == "wait":
            return [f"time.sleep(float({value} or 1))"]
        return [f"driver.find_element({locator}).click()"]

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
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(script_path.parent),
            capture_output=True,
            text=True,
            env=os.environ.copy(),
            timeout=self._timeout_seconds(),
        )
        failure = None
        if result.returncode != 0:
            failure = FailureInfo(
                script_path=str(script_path),
                line_num=0,
                broken_statement="",
                error_type="ReplayFailure",
                traceback=result.stderr,
                message="Migrated script failed during replay.",
            )
        return ReplayResult(result.returncode == 0, result.returncode, result.stdout, result.stderr, time.perf_counter() - started, failure)

    def _timeout_seconds(self) -> int | None:
        try:
            value = int(getattr(getattr(self.config, "trace", None), "script_timeout_seconds", 0) or 0)
        except Exception:
            value = 0
        return value if value > 0 else None
