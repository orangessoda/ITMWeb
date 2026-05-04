from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .schemas import BrowserType


ROOT_DIR = Path(__file__).resolve().parent.parent
PACKAGE_DIR = ROOT_DIR / "itmweb"
OUTPUT_DIR = PACKAGE_DIR / "output"
MINIMAX_DEFAULT_API_KEY = "sk-cp-18GlF0KOr4iPznt7BWcV_o_OTCCLdc4tv2YI6-1R3YrbrmtZwtbk0EKTddGEr0ZqDDED5BbEYI4zISF80NagyF2tMs8ubzwYBVLoD-Glsh0ge0MM23cMz-s"


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is not None:
        value = value.strip()
        if value:
            return value
    return default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _resolve_local_driver_path(browser_type: str, configured_path: str) -> str:
    configured_path = str(configured_path or "").strip()
    if configured_path and Path(configured_path).exists():
        return configured_path

    browser_key = str(browser_type or "").strip().lower()
    explicit_env = _env_str("ITMWEB_BROWSER_DRIVER_PATH", "")
    if explicit_env and Path(explicit_env).exists():
        return explicit_env

    candidates: list[Path] = []
    if browser_key == BrowserType.CHROME.value:
        candidates.append(Path(r"D:\chromedriver\chromedriver-win64\chromedriver-win64\chromedriver.exe"))
        cache_root = Path.home() / ".cache" / "selenium" / "chromedriver" / "win64"
        if cache_root.exists():
            candidates.extend(sorted(cache_root.glob("*/chromedriver.exe"), reverse=True))

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    executable_name = {
        BrowserType.CHROME.value: "chromedriver",
        BrowserType.EDGE.value: "msedgedriver",
        BrowserType.FIREFOX.value: "geckodriver",
    }.get(browser_key, "")
    if executable_name:
        discovered = shutil.which(executable_name)
        if discovered:
            return discovered
    return configured_path


@dataclass(slots=True)
class BrowserConfig:
    browser_type: str = BrowserType.CHROME.value
    headless: bool = False
    page_load_timeout: int = 30
    implicit_wait: int = 0
    explicit_wait: int = 10
    validation_wait: int = 3
    driver_path: str = ""
    browser_binary: str = ""
    window_size: str = "1920,1080"
    user_data_dir: str = ""
    force_no_proxy_server: bool = True
    use_isolated_user_data_dir: bool = True
    isolated_user_data_root: Path = OUTPUT_DIR / "_browser_profiles"
    allow_insecure_localhost: bool = True
    capture_interactable_limit: int = 120
    keep_browser_open: bool = False
    persist_snapshot_html: bool = False
    persist_snapshot_screenshot: bool = False


@dataclass(slots=True)
class ModelConfig:
    provider: str = "deepseek"
    model_name: str = "deepseek-v4-flash"
    api_base: str = "https://api.deepseek.com"
    api_key_env: str = "ITMWEB_DEEPSEEK_API_KEY"
    mode: str = "remote"
    api_key_value: str = "sk-72babea71fd9486e921a2faa3061d7d2"
    temperature: float = 0.1
    max_tokens: int = 2200
    strict_llm: bool = False
    timeout_seconds: int = 40

    @property
    def api_key(self) -> str:
        if self.api_key_value:
            return self.api_key_value
        direct_key = os.getenv("ITMWEB_API_KEY", "").strip()
        if direct_key:
            return direct_key
        return os.getenv(self.api_key_env, "")

    def public_metadata(self) -> dict[str, str]:
        return {
            "llm_provider": self.provider,
            "model_name": self.model_name,
            "api_base": self.api_base,
            "mode": self.mode,
        }


@dataclass(slots=True)
class MigrationConfig:
    top_k_candidates: int = 5
    max_attempts_per_breakpoint: int = 3
    max_dom_chars: int = 12000


@dataclass(slots=True)
class ArtifactConfig:
    artifact_root: Path = OUTPUT_DIR
    detail_level: str = "lean"
    persist_html: bool = False
    persist_screenshot: bool = False
    persist_candidates: bool = False
    persist_patch: bool = True
    persist_report: bool = True


@dataclass(slots=True)
class TraceConfig:
    script_timeout_seconds: int = 300
    stdout_tail_chars: int = 4000
    stderr_tail_chars: int = 4000
    keep_browser_on_trace_failure: bool = False
    hold_seconds_on_failure: int = 600000
    bootstrap_dir_name: str = "_bootstrap_trace"


@dataclass(slots=True)
class ProjectConfig:
    project_root: Path = ROOT_DIR
    package_root: Path = PACKAGE_DIR
    dataset_old_root: Path = ROOT_DIR / "datasetold"
    dataset_new_root: Path = ROOT_DIR / "datasetnew"
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    migration: MigrationConfig = field(default_factory=MigrationConfig)
    artifacts: ArtifactConfig = field(default_factory=ArtifactConfig)
    trace: TraceConfig = field(default_factory=TraceConfig)

    def ensure_directories(self) -> None:
        self.package_root.mkdir(parents=True, exist_ok=True)
        self.artifacts.artifact_root.mkdir(parents=True, exist_ok=True)


def load_config() -> ProjectConfig:
    config = ProjectConfig()
    provider = _env_str("ITMWEB_LLM_PROVIDER", _env_str("ITMWEB_MODEL_PROVIDER", config.model.provider)).lower()
    if provider not in {"deepseek", "minimax", "gpt"}:
        provider = "deepseek"
    config.model.provider = provider
    config.model.mode = _env_str("ITMWEB_MODEL_MODE", config.model.mode)
    if provider == "deepseek":
        config.model.model_name = _env_str("ITMWEB_DEEPSEEK_MODEL_NAME", "deepseek-v4-flash")
        config.model.api_base = _env_str("ITMWEB_DEEPSEEK_API_BASE", "https://api.deepseek.com")
        config.model.api_key_env = _env_str("ITMWEB_DEEPSEEK_API_KEY_ENV", "ITMWEB_DEEPSEEK_API_KEY")
        config.model.api_key_value = _env_str("ITMWEB_DEEPSEEK_API_KEY", config.model.api_key_value)
    elif provider == "gpt":
        config.model.model_name = _env_str("ITMWEB_GPT_MODEL_NAME", "gpt-4o-mini")
        config.model.api_base = _env_str("ITMWEB_GPT_API_BASE", "https://aihubmix.com/v1")
        config.model.api_key_env = _env_str("ITMWEB_GPT_API_KEY_ENV", "ITMWEB_GPT_API_KEY")
        config.model.api_key_value = _env_str("ITMWEB_GPT_API_KEY", config.model.api_key_value)
    else:
        config.model.model_name = _env_str("ITMWEB_MINIMAX_MODEL_NAME", "MiniMax-M2.7")
        config.model.api_base = _env_str("ITMWEB_MINIMAX_API_BASE", "https://api.minimaxi.com/v1")
        config.model.api_key_env = _env_str("ITMWEB_MINIMAX_API_KEY_ENV", "ITMWEB_MINIMAX_API_KEY")
        config.model.api_key_value = _env_str("ITMWEB_MINIMAX_API_KEY", MINIMAX_DEFAULT_API_KEY)
    config.model.model_name = _env_str("ITMWEB_MODEL_NAME", config.model.model_name)
    config.model.api_base = _env_str("ITMWEB_API_BASE", config.model.api_base)
    config.model.api_key_env = _env_str("ITMWEB_API_KEY_ENV", config.model.api_key_env)
    config.model.api_key_value = _env_str("ITMWEB_API_KEY", config.model.api_key_value)
    config.model.timeout_seconds = max(1, _env_int("ITMWEB_LLM_TIMEOUT_SECONDS", config.model.timeout_seconds))
    config.model.strict_llm = _env_str("ITMWEB_STRICT_LLM", "1" if config.model.strict_llm else "0") == "1"
    config.migration.max_attempts_per_breakpoint = max(
        1,
        _env_int("ITMWEB_MAX_ATTEMPTS_PER_BREAKPOINT", config.migration.max_attempts_per_breakpoint),
    )
    artifact_root = _env_str("ITMWEB_ARTIFACT_ROOT", str(config.artifacts.artifact_root))
    config.artifacts.artifact_root = Path(artifact_root)
    config.artifacts.detail_level = _env_str("ITMWEB_ARTIFACT_DETAIL", config.artifacts.detail_level).lower()
    config.artifacts.persist_html = _env_str("ITMWEB_PERSIST_HTML", "1" if config.artifacts.persist_html else "0") == "1"
    config.artifacts.persist_screenshot = (
        _env_str("ITMWEB_PERSIST_SCREENSHOT", "1" if config.artifacts.persist_screenshot else "0") == "1"
    )
    config.artifacts.persist_candidates = (
        _env_str("ITMWEB_PERSIST_CANDIDATES", "1" if config.artifacts.persist_candidates else "0") == "1"
    )
    config.artifacts.persist_patch = _env_str("ITMWEB_PERSIST_PATCH", "1" if config.artifacts.persist_patch else "0") == "1"
    config.artifacts.persist_report = _env_str("ITMWEB_PERSIST_REPORT", "1" if config.artifacts.persist_report else "0") == "1"
    config.browser.persist_snapshot_html = config.artifacts.persist_html
    config.browser.persist_snapshot_screenshot = config.artifacts.persist_screenshot
    config.browser.driver_path = _env_str("ITMWEB_BROWSER_DRIVER_PATH", config.browser.driver_path)
    config.browser.force_no_proxy_server = _env_str("ITMWEB_BROWSER_NO_PROXY_SERVER", "1") != "0"
    config.browser.use_isolated_user_data_dir = _env_str("ITMWEB_BROWSER_ISOLATED_PROFILE", "1") != "0"
    isolated_root = _env_str(
        "ITMWEB_BROWSER_ISOLATED_PROFILE_ROOT",
        str(config.browser.isolated_user_data_root),
    )
    config.browser.isolated_user_data_root = Path(isolated_root)
    config.browser.isolated_user_data_root.mkdir(parents=True, exist_ok=True)
    config.browser.driver_path = _resolve_local_driver_path(
        config.browser.browser_type,
        config.browser.driver_path,
    )
    config.ensure_directories()
    return config
