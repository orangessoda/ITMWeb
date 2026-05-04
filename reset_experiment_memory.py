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


def reset_mapping_library() -> int:
    if not MAPPING_PATH.parent.exists():
        MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)
    previous_count = 0
    if MAPPING_PATH.exists():
        previous_count = len(load_mapping_library().get("mappings", []))
    data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "mappings": [],
    }
    write_mapping_library(data)
    return previous_count


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


def output_app_dirs(app: str | None = None) -> list[Path]:
    if not OUTPUT_ROOT.exists():
        return []
    dirs = [path for path in OUTPUT_ROOT.iterdir() if path.is_dir() and not path.name.startswith("_")]
    if not app:
        return dirs
    return [path for path in dirs if app_matches(path.name, app)]


def delete_output_memory_files(app: str | None = None) -> dict[str, int]:
    if not OUTPUT_ROOT.exists():
        return {
            "old_intentions_deleted": 0,
            "llm_dialog_deleted": 0,
            "repair_states_deleted": 0,
        }
    counts = {
        "old_intentions_deleted": 0,
        "llm_dialog_deleted": 0,
        "repair_states_deleted": 0,
    }
    output_root = OUTPUT_ROOT.resolve()
    roots = output_app_dirs(app)
    for root in roots:
        for filename, count_key in [
            ("old_intentions.json", "old_intentions_deleted"),
            ("llm_dialog.jsonl", "llm_dialog_deleted"),
            ("repair_states.jsonl", "repair_states_deleted"),
        ]:
            for path in root.rglob(filename):
                resolved = path.resolve()
                if output_root not in resolved.parents:
                    raise RuntimeError(f"Refusing to delete outside output: {resolved}")
                path.unlink()
                counts[count_key] += 1
    return counts


def list_apps() -> None:
    names: set[str] = set()
    for path in output_app_dirs():
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
    parser = argparse.ArgumentParser(description="Reset ITMWeb experiment memory.")
    parser.add_argument(
        "--app",
        default="",
        help="Only clear experiment memory under this output app and mappings learned for the same app.",
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
    if app:
        removed_mappings = reset_mapping_library_for_app(app)
        deleted = delete_output_memory_files(app)
        matched_dirs = [path.name for path in output_app_dirs(app)]
        print("[ITMWeb] experiment memory reset")
        print(f"[ITMWeb] app={app}")
        print(f"[ITMWeb] matched_output_apps={matched_dirs}")
        print(f"[ITMWeb] mapping_library={MAPPING_PATH}")
        print(f"[ITMWeb] mappings_removed={removed_mappings}")
        print(f"[ITMWeb] old_intentions_deleted={deleted['old_intentions_deleted']}")
        print(f"[ITMWeb] llm_dialog_deleted={deleted['llm_dialog_deleted']}")
        print(f"[ITMWeb] repair_states_deleted={deleted['repair_states_deleted']}")
        return

    removed_mappings = reset_mapping_library()
    deleted = delete_output_memory_files()
    print("[ITMWeb] experiment memory reset")
    print("[ITMWeb] app=all")
    print(f"[ITMWeb] mapping_library={MAPPING_PATH}")
    print(f"[ITMWeb] mappings_removed={removed_mappings}")
    print(f"[ITMWeb] old_intentions_deleted={deleted['old_intentions_deleted']}")
    print(f"[ITMWeb] llm_dialog_deleted={deleted['llm_dialog_deleted']}")
    print(f"[ITMWeb] repair_states_deleted={deleted['repair_states_deleted']}")


if __name__ == "__main__":
    main()
