from __future__ import annotations

import hashlib
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schemas import ActionRecord, DOMSnapshot, ElementRecord, FulfillmentOption, ValidationResult, ValidationVerdict, utc_now

try:  # pragma: no cover - runtime dependency
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.support.ui import Select
except Exception:  # pragma: no cover
    webdriver = None  # type: ignore[assignment]
    By = None  # type: ignore[assignment]
    Keys = None  # type: ignore[assignment]
    ChromeService = None  # type: ignore[assignment]
    Select = None  # type: ignore[assignment]


@dataclass
class BrowserSession:
    config: Any
    driver: Any | None = None
    start_url: str = ""
    current_url: str = ""
    current_title: str = ""
    last_action_error: str = ""
    runtime_user_data_dir: str = ""

    @property
    def session(self) -> "BrowserSession":
        return self

    def open(self, start_url: str | None = None) -> None:
        if self.driver is None:
            self.driver = self._build_driver()
        if start_url:
            self.start_url = start_url
            self.navigate(start_url)

    def navigate(self, url: str) -> None:
        self.open() if self.driver is None else None
        self.driver.get(url)
        self._wait_for_document_ready()
        self._refresh_page_state()

    def close(self) -> None:
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        if self.runtime_user_data_dir:
            shutil.rmtree(self.runtime_user_data_dir, ignore_errors=True)
            self.runtime_user_data_dir = ""

    def snapshot(self, case_dir: Path | None = None) -> DOMSnapshot:
        self.open() if self.driver is None else None
        return DOMCollector(self).collect(case_dir)

    def execute_action(self, candidate: FulfillmentOption) -> ActionRecord:
        return ActionExecutor(self).execute(candidate)

    def validate_state(self, candidate: FulfillmentOption) -> ValidationResult:
        return ValidationResult(ValidationVerdict.PASSED.value, candidate_selector=candidate.selector)

    def _build_driver(self) -> Any:
        if webdriver is None:
            raise RuntimeError("selenium is not installed")
        options = webdriver.ChromeOptions()
        for arg in getattr(self.config, "chrome_args", []) or []:
            options.add_argument(arg)
        args = list(getattr(options, "arguments", []) or [])
        if getattr(self.config, "force_no_proxy_server", True) and "--no-proxy-server" not in args:
            options.add_argument("--no-proxy-server")
        if getattr(self.config, "force_no_proxy_server", True) and not any(arg.startswith("--proxy-bypass-list=") for arg in args):
            options.add_argument("--proxy-bypass-list=*.local;localhost;127.0.0.1")
        use_isolated_profile = getattr(
            self.config,
            "use_isolated_user_data_dir",
            getattr(self.config, "use_isolated_profile", True),
        )
        if use_isolated_profile and not any(arg.startswith("--user-data-dir=") for arg in args):
            root = Path(
                getattr(
                    self.config,
                    "isolated_user_data_root",
                    getattr(self.config, "tmp_profile_root", "") or tempfile.gettempdir(),
                )
            )
            root.mkdir(parents=True, exist_ok=True)
            self.runtime_user_data_dir = tempfile.mkdtemp(prefix="chrome_profile_", dir=str(root))
            options.add_argument(f"--user-data-dir={self.runtime_user_data_dir}")
        driver_path = str(getattr(self.config, "driver_path", "") or "").strip()
        if driver_path and ChromeService is not None:
            driver = webdriver.Chrome(service=ChromeService(driver_path), options=options)
        else:
            driver = webdriver.Chrome(options=options)
        width = int(getattr(self.config, "window_width", 1920) or 1920)
        height = int(getattr(self.config, "window_height", 1080) or 1080)
        driver.set_window_size(width, height)
        return driver

    def _wait_for_document_ready(self, timeout: int | None = None) -> None:
        if self.driver is None:
            return
        deadline = time.time() + (timeout or int(getattr(self.config, "page_load_timeout", 10) or 10))
        while time.time() < deadline:
            try:
                if self.driver.execute_script("return document.readyState") == "complete":
                    return
            except Exception:
                return
            time.sleep(0.1)

    def _refresh_page_state(self) -> None:
        if self.driver is None:
            return
        try:
            self.current_url = self.driver.current_url
            self.current_title = self.driver.title
        except Exception:
            pass


class DOMCollector:
    def __init__(self, session: BrowserSession) -> None:
        self.session = session

    def collect(self, case_dir: Path | None = None) -> DOMSnapshot:
        driver = self.session.driver
        html = driver.page_source if driver is not None else ""
        page_source_path = Path("")
        screenshot_path = Path("")
        if case_dir is not None:
            case_dir.mkdir(parents=True, exist_ok=True)
            page_source_path = case_dir / "page.html"
            page_source_path.write_text(html, encoding="utf-8", errors="ignore")
            screenshot_path = case_dir / "failure.png"
            try:
                driver.save_screenshot(str(screenshot_path))
            except Exception:
                screenshot_path = Path("")
        return DOMSnapshot(
            url=getattr(driver, "current_url", "") if driver else "",
            title=getattr(driver, "title", "") if driver else "",
            html=html,
            dom_excerpt=html[:4000],
            screenshot_path=str(screenshot_path) if screenshot_path else "",
            page_source_path=str(page_source_path),
            interactables=self.extract_interactables(html),
        )

    def extract_interactables(self, html: str) -> list[ElementRecord]:
        del html
        driver = self.session.driver
        if driver is None:
            return []
        items = driver.execute_script(
            """
            const nodes = Array.from(document.querySelectorAll('a,button,input,select,textarea,[role=button]')).slice(0, 100);
            function cssPath(el) {
              if (el.id) return '#' + CSS.escape(el.id);
              const parts = [];
              while (el && el.nodeType === Node.ELEMENT_NODE && parts.length < 5) {
                let part = el.tagName.toLowerCase();
                if (el.name) part += '[name="' + el.name.replace(/"/g, '\\"') + '"]';
                parts.unshift(part);
                el = el.parentElement;
              }
              return parts.join(' > ');
            }
            return nodes.map((el, index) => {
              const attrs = {};
              ['id','name','type','href','class','title','aria-label','role','value'].forEach(name => {
                if (el.hasAttribute && el.hasAttribute(name)) attrs[name] = el.getAttribute(name) || '';
              });
              return {
                index: index + 1,
                tag: (el.tagName || '').toLowerCase(),
                text: (el.innerText || el.textContent || '').trim(),
                attrs,
                css: cssPath(el),
                visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                enabled: !el.disabled
              };
            });
            """
        )
        records: list[ElementRecord] = []
        for item in items or []:
            attrs = {str(k): str(v) for k, v in dict(item.get("attrs", {})).items()}
            hint = f"id={attrs['id']}" if attrs.get("id") else (f"name={attrs['name']}" if attrs.get("name") else "")
            records.append(
                ElementRecord(
                    index=int(item.get("index", len(records) + 1)),
                    tag=str(item.get("tag", "")),
                    locator_hint=hint,
                    text=str(item.get("text", "")),
                    attributes=attrs,
                    is_visible=bool(item.get("visible", True)),
                    is_enabled=bool(item.get("enabled", True)),
                    css_selector=str(item.get("css", "")),
                )
            )
        return records

    def compress_dom(self, html: str) -> str:
        return html[:4000]


class ActionExecutor:
    def __init__(self, session: BrowserSession) -> None:
        self.session = session

    def execute(self, candidate: FulfillmentOption) -> ActionRecord:
        action = ActionRecord(candidate.action_type, candidate.selector, str(candidate.metadata.get("value", "")), candidate.explanation)
        try:
            element = self._resolve_element(candidate) if candidate.action_type != "wait" else None
            value = str(candidate.metadata.get("value", "") or "")
            if candidate.action_type == "click":
                element.click()
            elif candidate.action_type in {"input", "send_keys"}:
                if (element.get_attribute("type") or "").lower() != "file":
                    element.clear()
                element.send_keys(value)
            elif candidate.action_type == "clear":
                element.clear()
            elif candidate.action_type == "select":
                Select(element).select_by_visible_text(value)
            elif candidate.action_type == "submit":
                element.submit()
            elif candidate.action_type == "press_enter":
                element.send_keys(Keys.RETURN)
            elif candidate.action_type == "wait":
                time.sleep(float(value or 1))
            else:
                element.click()
            self.session._wait_for_document_ready()
            self.session._refresh_page_state()
            action.success = True
        except Exception as exc:
            self.session.last_action_error = str(exc)
            action.metadata["error"] = str(exc)
        finally:
            action.finished_at = utc_now()
        return action

    def _resolve_element(self, candidate: FulfillmentOption):
        by, value = self._selector_strategy(str(candidate.metadata.get("selector_type", "") or ""), candidate.selector)
        return self.session.driver.find_element(by, value)

    def _selector_strategy(self, selector_type: str, selector: str):
        selector_type = selector_type.lower().strip()
        if selector.startswith("id="):
            selector_type, selector = "id", selector.split("=", 1)[1]
        elif selector.startswith("name="):
            selector_type, selector = "name", selector.split("=", 1)[1]
        elif selector.startswith("xpath="):
            selector_type, selector = "xpath", selector.split("=", 1)[1]
        elif selector.startswith("css="):
            selector_type, selector = "css", selector.split("=", 1)[1]
        strategies = {
            "id": By.ID,
            "name": By.NAME,
            "xpath": By.XPATH,
            "css": By.CSS_SELECTOR,
            "link_text": By.LINK_TEXT,
            "partial_link_text": By.PARTIAL_LINK_TEXT,
            "class_name": By.CLASS_NAME,
            "tag_name": By.TAG_NAME,
        }
        if not selector_type:
            selector_type = "xpath" if selector.startswith(("/", "(")) else "css"
        return strategies.get(selector_type, By.CSS_SELECTOR), selector


class StateValidator:
    def __init__(self, session: BrowserSession) -> None:
        self.session = session

    def validate(self, candidate: FulfillmentOption) -> ValidationResult:
        return ValidationResult(ValidationVerdict.PASSED.value, candidate_selector=candidate.selector)
