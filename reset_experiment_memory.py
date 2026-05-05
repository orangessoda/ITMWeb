from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def find_project_root() -> Path:
    current = Path(__file__).resolve()
    for base in (current.parent, *current.parents):
        if (base / "itmweb" / "main.py").exists() and (base / "datasetnew").exists():
            return base
    raise RuntimeError("Could not locate ITMWeb project root.")


ROOT = find_project_root()
OUTPUT_ROOT = ROOT / "itmweb" / "output"
MAPPING_PATH = OUTPUT_ROOT / "intent_mapping_library.json"


def normalize_app_name(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if raw.endswith("_tests"):
        raw = raw[: -len("_tests")]
    raw = raw.replace("-", "_")
    parts = raw.split("_v", 1)
    return parts[0] if len(parts) == 2 and parts[1][:1].isdigit() else raw


def app_matches(value: str, app: str) -> bool:
    value_raw = str(value or "").strip().lower()
    app_raw = str(app or "").strip().lower()
    if not value_raw or not app_raw:
        return False
    return value_raw == app_raw or normalize_app_name(value_raw) == normalize_app_name(app_raw)


def mapping_app_values(mapping: dict) -> set[str]:
    values: set[str] = set()
    match = mapping.get("match") if isinstance(mapping.get("match"), dict) else {}
    for key in ["app_name", "suite_name", "learned_suite_name"]:
        if match.get(key):
            values.add(str(match[key]))
    for signature in mapping.get("source_signatures", []) if isinstance(mapping.get("source_signatures"), list) else []:
        if isinstance(signature, dict) and signature.get("suite_name"):
            values.add(str(signature["suite_name"]))
    mapping_id = str(mapping.get("mapping_id", "") or "")
    if mapping_id:
        values.add(mapping_id.split("_", 1)[0])
    return values


def load_mapping_library() -> dict:
    if not MAPPING_PATH.exists():
        return {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "mappings": [],
        }
    try:
        data = json.loads(MAPPING_PATH.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    mappings = data.get("mappings")
    if not isinstance(mappings, list):
        data["mappings"] = []
    return data


def write_mapping_library(data: dict) -> None:
    if not MAPPING_PATH.parent.exists():
        MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    MAPPING_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def reset_mapping_library_for_app(app: str) -> int:
    data = load_mapping_library()
    mappings = data.get("mappings", [])
    kept = []
    removed = 0
    for mapping in mappings:
        if not isinstance(mapping, dict):
            kept.append(mapping)
            continue
        if any(app_matches(value, app) for value in mapping_app_values(mapping)):
            removed += 1
        else:
            kept.append(mapping)
    data["mappings"] = kept
    write_mapping_library(data)
    return removed


def list_apps() -> None:
    names: set[str] = set()
    if OUTPUT_ROOT.exists():
        for path in OUTPUT_ROOT.iterdir():
            if path.is_dir() and not path.name.startswith("_"):
                names.add(path.name)
                normalized = normalize_app_name(path.name)
                if normalized:
                    names.add(normalized)
    for mapping in load_mapping_library().get("mappings", []):
        if isinstance(mapping, dict):
            names.update(value for value in mapping_app_values(mapping) if value)
    for name in sorted(names):
        print(name)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clear ITMWeb mapping memory for one app.")
    parser.add_argument(
        "--app",
        default="",
        help="Clear mappings learned for this app only, for example admidio or admidio_v4_2_0_tests.",
    )
    parser.add_argument(
        "--list-apps",
        action="store_true",
        help="List app names detected in output and mapping memory, then exit.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.list_apps:
        list_apps()
        return

    app = str(args.app or "").strip()
    if not app:
        raise SystemExit("Missing required --app. This script only clears mapping memory for one specified app.")
    removed_mappings = reset_mapping_library_for_app(app)
    print("[ITMWeb] mapping memory reset")
    print(f"[ITMWeb] app={app}")
    print(f"[ITMWeb] mapping_library={MAPPING_PATH}")
    print(f"[ITMWeb] mappings_removed={removed_mappings}")


if __name__ == "__main__":
    main()
