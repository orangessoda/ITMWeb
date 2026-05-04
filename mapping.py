from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schemas import ActionType, FulfillmentOption


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class IntentMappingLibrary:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.cache = self.default_payload()
        self.ensure()

    @staticmethod
    def default_payload() -> dict[str, Any]:
        return {"updated_at": "", "mappings": []}

    def ensure(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.cache = self.load()
            return
        payload = self.default_payload()
        payload["updated_at"] = utc_now()
        self.save(payload)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self.default_payload()
        return self._load_path(self.path)

    def _load_path(self, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self.default_payload()
        if not isinstance(payload, dict):
            return self.default_payload()
        mappings = payload.get("mappings", [])
        payload["mappings"] = mappings if isinstance(mappings, list) else []
        payload.setdefault("updated_at", "")
        return payload

    def save(self, payload: dict[str, Any]) -> None:
        normalized = payload if isinstance(payload, dict) else self.default_payload()
        normalized["updated_at"] = utc_now()
        mappings = normalized.get("mappings", [])
        normalized["mappings"] = mappings if isinstance(mappings, list) else []
        existing = self._load_path(self.path) if self.path.exists() else self.default_payload()
        merged = self._merge_mapping_payload(existing, normalized)
        self.cache = merged
        self.path.write_text(json.dumps(merged, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    def _merge_mapping_payload(self, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        existing_mappings = existing.get("mappings", []) if isinstance(existing, dict) else []
        incoming_mappings = incoming.get("mappings", []) if isinstance(incoming, dict) else []
        result: dict[str, Any] = {
            **(existing if isinstance(existing, dict) else {}),
            **{key: value for key, value in incoming.items() if key != "mappings"},
            "updated_at": utc_now(),
            "mappings": [],
        }
        index_by_key: dict[str, int] = {}
        for mapping in existing_mappings if isinstance(existing_mappings, list) else []:
            if not isinstance(mapping, dict):
                continue
            result["mappings"].append(mapping)
            for key in self._mapping_upsert_keys(mapping):
                index_by_key.setdefault(key, len(result["mappings"]) - 1)
        for mapping in incoming_mappings if isinstance(incoming_mappings, list) else []:
            if not isinstance(mapping, dict):
                continue
            keys = self._mapping_upsert_keys(mapping)
            existing_index = next((index_by_key[key] for key in keys if key in index_by_key), -1)
            if existing_index >= 0:
                result["mappings"][existing_index] = self._merge_mapping_entry(result["mappings"][existing_index], mapping)
                for key in self._mapping_upsert_keys(result["mappings"][existing_index]):
                    index_by_key[key] = existing_index
            else:
                result["mappings"].append(mapping)
                for key in keys:
                    index_by_key[key] = len(result["mappings"]) - 1
        return result

    def _mapping_upsert_keys(self, mapping: dict[str, Any]) -> list[str]:
        keys: list[str] = []
        mapping_id = str(mapping.get("mapping_id", "") or "").strip().lower()
        if mapping_id:
            keys.append(f"id:{mapping_id}")
        recipe_id = str(mapping.get("recipe_id", "") or "").strip().lower()
        if recipe_id:
            keys.append(f"recipe:{recipe_id}")
        match = mapping.get("match", {}) if isinstance(mapping.get("match", {}), dict) else {}
        intent_key = str(match.get("intent_key", "") or "").strip().lower()
        if intent_key:
            keys.append(f"intent:{intent_key}")
        for item in match.get("intent_keys", []) if isinstance(match.get("intent_keys", []), list) else []:
            value = str(item or "").strip().lower()
            if value:
                keys.append(f"intent:{value}")
        for source in mapping.get("source_signatures", []) if isinstance(mapping.get("source_signatures", []), list) else []:
            if not isinstance(source, dict):
                continue
            source_key = str(source.get("source_key", "") or "").strip().lower()
            if source_key:
                keys.append(f"source:{source_key}")
        return self.unique(keys)

    def _merge_mapping_entry(self, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = {**existing, **incoming}
        if existing.get("created_at"):
            merged["created_at"] = existing["created_at"]
        if existing.get("mapping_id") and not incoming.get("mapping_id"):
            merged["mapping_id"] = existing["mapping_id"]
        if existing.get("recipe_id") and not incoming.get("recipe_id"):
            merged["recipe_id"] = existing["recipe_id"]
        merged["updated_at"] = utc_now()
        merged["match"] = self._merge_match_payload(
            existing.get("match", {}) if isinstance(existing.get("match", {}), dict) else {},
            incoming.get("match", {}) if isinstance(incoming.get("match", {}), dict) else {},
        )
        merged["source_signatures"] = self._merge_unique_dict_list(
            existing.get("source_signatures", []),
            incoming.get("source_signatures", []),
            "source_key",
            30,
        )
        merged["target_recipes"] = self._merge_unique_dict_list(
            existing.get("target_recipes", []),
            incoming.get("target_recipes", []),
            "recipe_id",
            12,
        )
        merged["merge_reasons"] = self.unique(
            [str(item) for item in existing.get("merge_reasons", []) if str(item).strip()]
            + [str(item) for item in incoming.get("merge_reasons", []) if str(item).strip()]
        )[:8]
        merged["stats"] = self._merge_stats(
            existing.get("stats", {}) if isinstance(existing.get("stats", {}), dict) else {},
            incoming.get("stats", {}) if isinstance(incoming.get("stats", {}), dict) else {},
        )
        return merged

    def _merge_unique_dict_list(self, existing: Any, incoming: Any, key: str, limit: int) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        index_by_key: dict[str, int] = {}
        for item in (existing if isinstance(existing, list) else []) + (incoming if isinstance(incoming, list) else []):
            if not isinstance(item, dict):
                continue
            item_key = str(item.get(key, "") or "").strip()
            if item_key and item_key in index_by_key:
                current = result[index_by_key[item_key]]
                created_at = current.get("created_at", item.get("created_at", ""))
                result[index_by_key[item_key]] = {**current, **item, "created_at": created_at}
            else:
                if item_key:
                    index_by_key[item_key] = len(result)
                result.append(item)
        return result[:limit]

    def _merge_stats(self, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = {**existing, **incoming}
        for key in ["learned_count", "hit_count", "success_count", "failure_count"]:
            merged[key] = int(existing.get(key, 0) or 0) + int(incoming.get(key, 0) or 0)
        for key in ["last_learned_at", "last_matched_at", "last_success_at", "last_failure_at"]:
            merged[key] = max(str(existing.get(key, "") or ""), str(incoming.get(key, "") or ""))
        return merged

    @staticmethod
    def unique(items: list[str]) -> list[str]:
        seen: list[str] = []
        for item in items:
            if item and item not in seen:
                seen.append(item)
        return seen

    @staticmethod
    def extract_terms(text: str) -> list[str]:
        return re.findall(r"[a-zA-Z_][a-zA-Z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", str(text or "").lower())

    def signal_terms(self, text: str, limit: int, *, page: bool = False) -> list[str]:
        noise = {
            "http",
            "https",
            "local",
            "localhost",
            "html",
            "head",
            "body",
            "script",
            "style",
            "class",
            "lang",
            "php",
            "modules",
            "system",
            "driver",
            "find",
            "find_element",
            "element",
            "xpath",
            "css",
            "action_type",
            "locator",
            "time",
            "sleep",
            "old",
            "new",
            "the",
            "and",
            "for",
            "with",
            "using",
            "already",
            "entered",
            "expects",
            "detail",
            "value",
            "flow",
            "next",
        }
        if page:
            noise.update({"overview", "page", "container", "row", "col", "div", "span"})
        else:
            noise.update({"page"})
        terms: list[str] = []
        for token in self.extract_terms(text):
            cleaned = token.strip().lower()
            if len(cleaned) < 3 or cleaned in noise:
                continue
            if re.fullmatch(r"v?\d+(?:_\d+)*", cleaned):
                continue
            if cleaned not in terms:
                terms.append(cleaned)
            if len(terms) >= limit:
                break
        return terms

    @staticmethod
    def app_name(suite_name: str, script_path: str = "") -> str:
        suite = str(suite_name or "").strip().lower()
        if suite:
            stripped = re.sub(r"(_v\d+(?:_\d+)*)?_tests?$", "", suite)
            stripped = re.sub(r"_tests?$", "", stripped)
            if stripped:
                return stripped
        script = Path(script_path) if script_path else None
        if script is not None and script.parent.name:
            parent = script.parent.name.strip().lower()
            stripped = re.sub(r"(_v\d+(?:_\d+)*)?_tests?$", "", parent)
            stripped = re.sub(r"_tests?$", "", stripped)
            if stripped:
                return stripped
        return suite or "global"

    @staticmethod
    def infer_business_action(business_goal: str, action_type: str, text: str) -> str:
        goal = str(business_goal or "").strip().lower() or "generic"
        action = str(action_type or "").strip().lower() or "click"
        blob = str(text or "").strip().lower()
        if goal == "login" or any(token in blob for token in ["sign in", "signin", "login", "log in"]):
            if action in {"input", "send_keys", "clear", "clear_and_enter"}:
                return "login_input"
            if any(token in blob for token in ["username", "password", "usr_login", "usr_password"]):
                return "login_input"
            if any(token in blob for token in ["submit", "button", "next_page", "plg_btn_login", "sign in", "login"]):
                return "login_submit"
        if goal in {"logout", "create", "edit", "delete", "upload", "search"}:
            return f"{goal}_{action}"
        return f"{goal}_{action}"

    def page_gate_terms(self, text: str, business_goal: str, selector: str = "") -> list[str]:
        blob = " ".join([str(text or ""), str(selector or ""), str(business_goal or "")]).lower()
        terms = self.signal_terms(blob, 12, page=True)
        preferred: list[str] = []
        goal = str(business_goal or "").strip().lower()
        if goal == "login":
            for token in [
                "login",
                "signin",
                "sign",
                "username",
                "password",
                "plg_usr_login_name",
                "plg_usr_password",
                "plg_btn_login",
            ]:
                if token in blob and token not in preferred:
                    preferred.append(token)
        return self.unique(preferred + terms)[:6]

    @staticmethod
    def detect_selector_type(selector: str) -> str:
        raw = str(selector or "").strip()
        if not raw:
            return ""
        if "=" in raw:
            prefix = raw.split("=", 1)[0].strip().lower()
            if prefix:
                return prefix
        if raw.startswith("//") or raw.startswith("(//"):
            return "xpath"
        if raw.startswith("#") or raw.startswith(".") or ">" in raw or "[" in raw:
            return "css"
        return ""

    @staticmethod
    def term_present(term: str, text: str) -> bool:
        normalized = str(term or "").strip().lower()
        if not normalized:
            return False
        return normalized in str(text or "").lower()

    @staticmethod
    def _stable_hash(payload: Any, length: int = 12) -> str:
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:length]

    @staticmethod
    def _compact_step(step: dict[str, Any]) -> dict[str, str]:
        return {
            "action_type": str(step.get("action_type", "") or "").strip().lower(),
            "selector": str(step.get("selector", "") or "").strip(),
            "selector_type": str(step.get("selector_type", "") or "").strip().lower(),
            "value": str(step.get("value", "") or ""),
        }

    def recipe_id(self, recipe_steps: list[dict[str, Any]]) -> str:
        compact_steps = [self._compact_step(step) for step in recipe_steps if isinstance(step, dict)]
        return f"recipe_{self._stable_hash(compact_steps)}"

    def source_signature_key(self, runtime_signature: dict[str, Any]) -> str:
        payload = {
            "app": str(runtime_signature.get("app_name", "") or "").strip().lower(),
            "goal": str(runtime_signature.get("business_goal", "") or "").strip().lower(),
            "business_action": str(runtime_signature.get("business_action", "") or "").strip().lower(),
            "family": str(runtime_signature.get("action_family", "") or "").strip().lower(),
            "intent": str(runtime_signature.get("intent_name", "") or "").strip().lower(),
            "phase": str(runtime_signature.get("phase", "") or "").strip().lower(),
            "small_intention": str(runtime_signature.get("small_intention", "") or "").strip().lower(),
            "segment_terms": [
                str(item).strip().lower()
                for item in runtime_signature.get("segment_intent_terms", [])[:10]
                if str(item).strip()
            ],
            "action_chain_terms": [
                str(item).strip().lower()
                for item in runtime_signature.get("action_chain_terms", [])[:10]
                if str(item).strip()
            ],
            "source_terms": [str(item).strip().lower() for item in runtime_signature.get("source_terms", [])[:5] if str(item).strip()],
        }
        return f"source_{self._stable_hash(payload)}"

    def intent_key(self, runtime_signature: dict[str, Any]) -> str:
        app = str(runtime_signature.get("app_name", "") or "global").strip().lower() or "global"
        goal = str(runtime_signature.get("business_goal", "") or "generic").strip().lower() or "generic"
        business_action = str(runtime_signature.get("business_action", "") or "").strip().lower()
        action = str(runtime_signature.get("action_type", "") or "click").strip().lower() or "click"
        segment_terms = [
            str(item).strip().lower()
            for item in runtime_signature.get("segment_intent_terms", [])
            if str(item).strip()
        ]
        action_chain_terms = [
            str(item).strip().lower()
            for item in runtime_signature.get("action_chain_terms", [])
            if str(item).strip()
        ]
        phase = str(runtime_signature.get("phase", "") or "").strip().lower()
        small_intention = str(runtime_signature.get("small_intention", "") or "").strip().lower()
        if segment_terms or action_chain_terms or small_intention:
            role_terms = self.unique(
                [phase]
                + segment_terms[:8]
                + action_chain_terms[:8]
                + self.signal_terms(small_intention, 8)
            )[:14]
            role = "_".join(re.sub(r"[^a-z0-9]+", "_", term).strip("_") for term in role_terms if term)[:80]
            if not role:
                role = self._stable_hash([phase, small_intention, segment_terms, action_chain_terms], 8)
            return ".".join([app, goal, business_action or "action", action, role])
        blob = " ".join(
            [
                str(runtime_signature.get("source_statement", "") or ""),
                str(runtime_signature.get("target_role", "") or ""),
                " ".join(str(item) for item in runtime_signature.get("source_terms", []) if str(item).strip()),
                " ".join(str(item) for item in runtime_signature.get("target_role_terms", []) if str(item).strip()),
            ]
        ).lower()
        if goal == "login" or business_action.startswith("login_"):
            if business_action == "login_submit" or any(term in blob for term in ["submit", "button", "next_page", "plg_btn_login", "adm_button_login"]):
                role = "submit"
            elif any(term in blob for term in ["password", "passwd", "pwd", "usr_password", "plg_usr_password"]):
                role = "password"
            elif any(term in blob for term in ["username", "user name", "login_name", "usr_login", "plg_usr_login_name", "user"]):
                role = "username"
            else:
                role = "field"
            return ".".join([app, "login", role, action])
        role_terms = [
            str(item).strip().lower()
            for item in runtime_signature.get("target_role_terms", []) + runtime_signature.get("source_terms", [])
            if str(item).strip()
        ]
        noise = {
            "target",
            "intention",
            "click",
            "input",
            "enter",
            "field",
            "button",
            "menu",
            "item",
            "admin",
            "page",
        }
        role = next((term for term in role_terms if term not in noise), "")
        if not role:
            role = self._stable_hash(blob or runtime_signature, 8)
        return ".".join([app, goal, business_action or action, role, action])

    def mapping_intent_keys(self, mapping: dict[str, Any]) -> list[str]:
        match = mapping.get("match", {}) if isinstance(mapping.get("match", {}), dict) else {}
        keys = [str(match.get("intent_key", "") or "").strip().lower()]
        for item in match.get("intent_keys", []) if isinstance(match.get("intent_keys", []), list) else []:
            keys.append(str(item or "").strip().lower())
        if not any(keys):
            inferred = self.intent_key(
                {
                    "app_name": str(match.get("app_name", "") or ""),
                    "business_goal": str(match.get("business_goal", "") or ""),
                    "business_action": str(match.get("business_action", "") or ""),
                    "action_type": str(match.get("action_type", "") or ""),
                    "source_statement": str(match.get("target_role", "") or ""),
                    "target_role": str(match.get("target_role", "") or ""),
                    "source_terms": match.get("source_terms", []) if isinstance(match.get("source_terms", []), list) else [],
                    "target_role_terms": match.get("target_role_terms", []) if isinstance(match.get("target_role_terms", []), list) else [],
                }
            )
            keys.append(inferred)
        return self.unique([key for key in keys if key])

    def source_signature_payload(self, runtime_signature: dict[str, Any]) -> dict[str, Any]:
        target_role = str(runtime_signature.get("target_role", "") or "").strip()
        return {
            "source_key": self.source_signature_key(runtime_signature),
            "intent_key": str(runtime_signature.get("intent_key", "") or self.intent_key(runtime_signature)),
            "learned_from_case": str(runtime_signature.get("case_id", "") or ""),
            "suite_name": str(runtime_signature.get("suite_name", "") or ""),
            "intent_name": str(runtime_signature.get("intent_name", "") or ""),
            "source_statement": str(runtime_signature.get("source_statement", "") or ""),
            "locator_hint": str(runtime_signature.get("locator_hint", "") or ""),
            "target_role": target_role,
            "target_role_terms": self.signal_terms(target_role, 8),
            "source_terms": [str(item) for item in runtime_signature.get("source_terms", []) if str(item).strip()][:12],
            "context_terms": [str(item) for item in runtime_signature.get("context_terms", []) if str(item).strip()][:10],
            "page_terms": [str(item) for item in runtime_signature.get("page_terms", []) if str(item).strip()][:10],
            "phase": str(runtime_signature.get("phase", "") or ""),
            "small_intention": str(runtime_signature.get("small_intention", "") or ""),
            "expected_result": str(runtime_signature.get("expected_result", "") or ""),
            "segment_intent_terms": [
                str(item) for item in runtime_signature.get("segment_intent_terms", []) if str(item).strip()
            ][:14],
            "action_chain_terms": [
                str(item) for item in runtime_signature.get("action_chain_terms", []) if str(item).strip()
            ][:14],
            "expected_terms": [str(item) for item in runtime_signature.get("expected_terms", []) if str(item).strip()][:10],
            "created_at": utc_now(),
        }

    def mapping_cardinality(self, mapping: dict[str, Any], recipe_steps: list[dict[str, Any]]) -> str:
        source_signatures = mapping.get("source_signatures", [])
        source_count = len(source_signatures) if isinstance(source_signatures, list) and source_signatures else 1
        step_count = len(recipe_steps) if recipe_steps else 1
        if source_count > 1 and step_count > 1:
            return "many_to_many"
        if source_count > 1:
            return "many_to_one"
        if step_count > 1:
            return "one_to_many"
        return "one_to_one"

    def _select_target_recipe(self, mapping: dict[str, Any]) -> dict[str, Any]:
        target_recipes = mapping.get("target_recipes", [])
        valid_recipes = [item for item in target_recipes if isinstance(item, dict) and isinstance(item.get("steps"), list)]
        if valid_recipes:
            return sorted(
                valid_recipes,
                key=lambda item: (
                    int((item.get("stats", {}) or {}).get("success_count", 0) or 0),
                    int((item.get("stats", {}) or {}).get("hit_count", 0) or 0),
                    str(item.get("updated_at", "") or item.get("created_at", "")),
                ),
                reverse=True,
            )[0]
        recipe = mapping.get("recipe", {}) if isinstance(mapping.get("recipe", {}), dict) else {}
        return {
            "recipe_id": str(mapping.get("recipe_id", "") or ""),
            "summary": str(recipe.get("summary", "") or ""),
            "steps": recipe.get("steps", []),
            "stats": {},
        }

    def _merge_terms(self, existing: list[Any], incoming: list[Any], limit: int) -> list[str]:
        return self.unique([str(item).strip().lower() for item in existing + incoming if str(item).strip()])[:limit]

    def _merge_match_payload(self, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = {**existing, **incoming}
        for field_name, limit in [
            ("source_terms", 16),
            ("context_terms", 14),
            ("page_terms", 14),
            ("target_role_terms", 12),
            ("segment_intent_terms", 18),
            ("action_chain_terms", 18),
            ("expected_terms", 12),
            ("required_page_terms", 10),
            ("forbidden_page_terms", 10),
        ]:
            merged[field_name] = self._merge_terms(
                existing.get(field_name, []) if isinstance(existing.get(field_name, []), list) else [],
                incoming.get(field_name, []) if isinstance(incoming.get(field_name, []), list) else [],
                limit,
            )
        source_locators = existing.get("source_locators", [])
        if not isinstance(source_locators, list):
            source_locators = []
        merged["source_locators"] = self.unique(
            [str(item) for item in source_locators if str(item).strip()]
            + [str(existing.get("locator_hint", "") or ""), str(incoming.get("locator_hint", "") or "")]
        )[:8]
        if existing.get("locator_hint"):
            merged["locator_hint"] = existing.get("locator_hint")
        merged["intent_keys"] = self.unique(
            [
                str(existing.get("intent_key", "") or "").strip().lower(),
                str(incoming.get("intent_key", "") or "").strip().lower(),
                *(
                    str(item or "").strip().lower()
                    for item in existing.get("intent_keys", [])
                    if isinstance(existing.get("intent_keys", []), list)
                ),
                *(
                    str(item or "").strip().lower()
                    for item in incoming.get("intent_keys", [])
                    if isinstance(incoming.get("intent_keys", []), list)
                ),
            ]
        )[:12]
        return merged

    def _append_source_signature(self, entry: dict[str, Any], source_payload: dict[str, Any]) -> None:
        source_signatures = entry.setdefault("source_signatures", [])
        if not isinstance(source_signatures, list):
            source_signatures = []
            entry["source_signatures"] = source_signatures
        source_key = str(source_payload.get("source_key", "") or "")
        for item in source_signatures:
            if isinstance(item, dict) and str(item.get("source_key", "") or "") == source_key:
                item.update({**source_payload, "created_at": str(item.get("created_at", "") or source_payload.get("created_at", ""))})
                return
        source_signatures.append(source_payload)
        del source_signatures[30:]

    def _upsert_target_recipe(self, entry: dict[str, Any], target_recipe: dict[str, Any]) -> dict[str, Any]:
        target_recipes = entry.setdefault("target_recipes", [])
        if not isinstance(target_recipes, list):
            target_recipes = []
            entry["target_recipes"] = target_recipes
        recipe_id = str(target_recipe.get("recipe_id", "") or "")
        for existing in target_recipes:
            if isinstance(existing, dict) and str(existing.get("recipe_id", "") or "") == recipe_id:
                existing_stats = existing.get("stats", {}) if isinstance(existing.get("stats", {}), dict) else {}
                existing.update({**target_recipe, "created_at": str(existing.get("created_at", "") or target_recipe.get("created_at", ""))})
                existing["stats"] = existing_stats
                stats = existing.setdefault("stats", {})
                stats["learned_count"] = int(stats.get("learned_count", 0) or 0) + 1
                stats["success_count"] = int(stats.get("success_count", 0) or 0) + 1
                stats["last_learned_at"] = utc_now()
                stats["last_success_at"] = utc_now()
                return existing
        target_recipe.setdefault(
            "stats",
            {
                "learned_count": 1,
                "hit_count": 0,
                "success_count": 1,
                "last_learned_at": utc_now(),
                "last_success_at": utc_now(),
            },
        )
        target_recipes.append(target_recipe)
        del target_recipes[12:]
        return target_recipe

    def _best_source_signature_match(
        self,
        mapping: dict[str, Any],
        runtime_signature: dict[str, Any],
    ) -> tuple[float, list[str]]:
        source_signatures = mapping.get("source_signatures", [])
        if not isinstance(source_signatures, list):
            return 0.0, []
        runtime_source_key = self.source_signature_key(runtime_signature)
        runtime_terms = [str(item).strip().lower() for item in runtime_signature.get("source_terms", []) if str(item).strip()]
        runtime_context_terms = [
            str(item).strip().lower() for item in runtime_signature.get("context_terms", []) if str(item).strip()
        ]
        runtime_role_terms = [
            str(item).strip().lower() for item in runtime_signature.get("target_role_terms", []) if str(item).strip()
        ]
        runtime_segment_terms = [
            str(item).strip().lower() for item in runtime_signature.get("segment_intent_terms", []) if str(item).strip()
        ]
        runtime_chain_terms = [
            str(item).strip().lower() for item in runtime_signature.get("action_chain_terms", []) if str(item).strip()
        ]
        runtime_locator = str(runtime_signature.get("locator_hint", "") or "").strip().lower()
        best_score = 0.0
        best_terms: list[str] = []
        for source in source_signatures:
            if not isinstance(source, dict):
                continue
            score = 0.0
            matched_terms: list[str] = []
            if str(source.get("source_key", "") or "") == runtime_source_key:
                score += 0.28
            source_terms = [str(item).strip().lower() for item in source.get("source_terms", []) if str(item).strip()]
            context_terms = [str(item).strip().lower() for item in source.get("context_terms", []) if str(item).strip()]
            role_terms = [str(item).strip().lower() for item in source.get("target_role_terms", []) if str(item).strip()]
            segment_terms = [str(item).strip().lower() for item in source.get("segment_intent_terms", []) if str(item).strip()]
            chain_terms = [str(item).strip().lower() for item in source.get("action_chain_terms", []) if str(item).strip()]
            source_overlap = [token for token in runtime_terms if token in source_terms]
            context_overlap = [token for token in runtime_context_terms if token in context_terms]
            role_overlap = [token for token in runtime_role_terms if token in role_terms]
            segment_overlap = [token for token in runtime_segment_terms if token in segment_terms]
            chain_overlap = [token for token in runtime_chain_terms if token in chain_terms]
            matched_terms.extend(source_overlap + context_overlap + role_overlap + segment_overlap + chain_overlap)
            score += min(0.30, 0.10 * len(segment_overlap))
            score += min(0.22, 0.055 * len(chain_overlap))
            score += min(0.18, 0.045 * len(source_overlap))
            score += min(0.08, 0.025 * len(context_overlap))
            score += min(0.10, 0.05 * len(role_overlap))
            source_locator = str(source.get("locator_hint", "") or "").strip().lower()
            if runtime_locator and source_locator and runtime_locator == source_locator:
                score += 0.02
            if score > best_score:
                best_score = score
                best_terms = matched_terms
        return best_score, self.unique(best_terms)

    def candidate_from_entry(
        self,
        mapping: dict[str, Any],
        runtime_signature: dict[str, Any],
        match_score: float,
        matched_terms: list[str],
    ) -> FulfillmentOption | None:
        intent_recipe = mapping.get("intent_recipe", {})
        if not isinstance(intent_recipe, dict):
            intent_recipe = {}
        recipe = mapping.get("recipe", {})
        if not isinstance(recipe, dict):
            recipe = {}
        selected_recipe = self._select_target_recipe(mapping)
        recipe_steps = selected_recipe.get("steps") or intent_recipe.get("steps") or recipe.get("steps", [])
        if not isinstance(recipe_steps, list) or not recipe_steps:
            return None
        primary = recipe_steps[0] if isinstance(recipe_steps[0], dict) else {}
        binding = intent_recipe.get("binding", {})
        if not isinstance(binding, dict):
            binding = {}
        primary = {**binding, **primary}
        selector = str(primary.get("selector", "") or "").strip()
        action_type = str(primary.get("action_type", "") or runtime_signature.get("action_type", "click")).strip().lower()
        if not selector and action_type != ActionType.WAIT.value:
            return None
        selector_type = str(primary.get("selector_type", "") or self.detect_selector_type(selector)).strip().lower()
        target_role = str(intent_recipe.get("target_role", "") or mapping.get("match", {}).get("target_role", "") or "").strip()
        business_cues = [str(item) for item in intent_recipe.get("business_cues", []) if str(item).strip()]
        oracle_cues = [str(item) for item in intent_recipe.get("oracle_cues", []) if str(item).strip()]
        page_gate = intent_recipe.get("page_gate", {}) if isinstance(intent_recipe.get("page_gate", {}), dict) else {}
        confidence = min(0.99, max(0.58, 0.46 + match_score))
        explanation = (
            f"Intent recipe memory '{mapping.get('mapping_id', '')}' matched target role "
            f"'{target_role or runtime_signature.get('target_role', '')}' with score {match_score:.2f}."
        ).strip()
        match = mapping.get("match", {}) if isinstance(mapping.get("match", {}), dict) else {}
        source_signatures = mapping.get("source_signatures", [])
        source_signature_count = len(source_signatures) if isinstance(source_signatures, list) and source_signatures else 1
        target_recipes = mapping.get("target_recipes", [])
        target_recipe_count = len(target_recipes) if isinstance(target_recipes, list) and target_recipes else 1
        target_recipe_id = str(selected_recipe.get("recipe_id", "") or mapping.get("recipe_id", "") or "")
        return FulfillmentOption(
            source="intent_mapping",
            action_type=action_type,
            selector=selector or "trace:wait",
            confidence=round(confidence, 4),
            score_breakdown={
                "intent_mapping_bonus": round(match_score, 4),
                "total": round(confidence, 4),
            },
            explanation=explanation,
            patch_statement=str(primary.get("patch_statement", "") or ""),
            metadata={
                "selector_type": selector_type,
                "value": str(primary.get("value", "") or ""),
                "intent_mapping_id": str(mapping.get("mapping_id", "") or ""),
                "intent_mapping_score": round(match_score, 4),
                "intent_mapping_match_terms": list(matched_terms),
                "intent_mapping_recipe_summary": str(selected_recipe.get("summary", "") or recipe.get("summary", "") or ""),
                "intent_mapping_business_action": str(match.get("business_action", "") or ""),
                "intent_mapping_execution_action": action_type,
                "target_recipe_id": target_recipe_id,
                "target_recipe_count": target_recipe_count,
                "source_signature_count": source_signature_count,
                "mapping_cardinality": self.mapping_cardinality(mapping, [step for step in recipe_steps if isinstance(step, dict)]),
                "target_role": target_role,
                "target_text": target_role,
                "business_cues": business_cues,
                "oracle_cues": oracle_cues,
                "page_gate_required_terms": [str(item) for item in page_gate.get("required_terms", []) if str(item).strip()],
                "page_gate_forbidden_terms": [str(item) for item in page_gate.get("forbidden_terms", []) if str(item).strip()],
                "outcome_contract": str(intent_recipe.get("outcome_contract", "") or primary.get("expected_outcome", "")),
                "mapped_recipe_steps": [step for step in recipe_steps if isinstance(step, dict)],
                "retry_hints": ["prefer_learned_intent_mapping_recipe", "respect_intent_recipe_page_gate"],
                "retry_notes": explanation,
                "plan_source": "learned_intent_mapping",
                "business_goal": str(match.get("business_goal", "") or ""),
            },
        )

    def match_mapping(
        self,
        mapping: dict[str, Any],
        runtime_signature: dict[str, Any],
    ) -> tuple[float, list[str]]:
        match = mapping.get("match", {})
        if not isinstance(match, dict):
            return 0.0, []
        app_name = str(match.get("app_name", "") or "").strip().lower()
        if app_name and app_name != runtime_signature["app_name"]:
            return 0.0, []
        suite_name = str(match.get("suite_name", "") or "").strip()
        suite_matches = bool(suite_name and suite_name == runtime_signature["suite_name"])
        mapping_goal = str(match.get("business_goal", "") or "").strip().lower()
        runtime_goal = str(runtime_signature.get("business_goal", "") or "").strip().lower()
        if (
            mapping_goal
            and runtime_goal
            and mapping_goal not in {"generic", "navigate"}
            and runtime_goal not in {"generic", "navigate"}
            and mapping_goal != runtime_goal
        ):
            return 0.0, []
        mapping_family = str(match.get("action_family", "") or "").strip().lower()
        mapping_action = str(match.get("action_type", "") or "").strip().lower()
        mapping_business_action = str(match.get("business_action", "") or "").strip().lower()
        runtime_family = str(runtime_signature.get("action_family", "") or "").strip().lower()
        runtime_business_action = str(runtime_signature.get("business_action", "") or "").strip().lower()
        login_submit_family_compatible = (
            mapping_business_action == "login_submit"
            and runtime_business_action == "login_submit"
            and mapping_family in {"click_family", "submit_family", "generic_family"}
            and runtime_family in {"click_family", "submit_family", "generic_family"}
        )
        if mapping_family and mapping_family != runtime_family and not login_submit_family_compatible:
            return 0.0, []
        if (
            mapping_business_action
            and runtime_business_action
            and mapping_business_action != runtime_business_action
        ):
            return 0.0, []
        source_terms = [str(item).strip().lower() for item in match.get("source_terms", []) if str(item).strip()]
        context_terms = [str(item).strip().lower() for item in match.get("context_terms", []) if str(item).strip()]
        page_terms = [str(item).strip().lower() for item in match.get("page_terms", []) if str(item).strip()]
        target_role_terms = [str(item).strip().lower() for item in match.get("target_role_terms", []) if str(item).strip()]
        segment_terms = [str(item).strip().lower() for item in match.get("segment_intent_terms", []) if str(item).strip()]
        action_chain_terms = [str(item).strip().lower() for item in match.get("action_chain_terms", []) if str(item).strip()]
        expected_terms = [str(item).strip().lower() for item in match.get("expected_terms", []) if str(item).strip()]
        runtime_role_terms = [str(item).strip().lower() for item in runtime_signature.get("target_role_terms", []) if str(item).strip()]
        runtime_segment_terms = [
            str(item).strip().lower() for item in runtime_signature.get("segment_intent_terms", []) if str(item).strip()
        ]
        runtime_chain_terms = [
            str(item).strip().lower() for item in runtime_signature.get("action_chain_terms", []) if str(item).strip()
        ]
        runtime_expected_terms = [
            str(item).strip().lower() for item in runtime_signature.get("expected_terms", []) if str(item).strip()
        ]
        runtime_intent_key = str(runtime_signature.get("intent_key", "") or self.intent_key(runtime_signature)).strip().lower()
        intent_keys = self.mapping_intent_keys(mapping)
        intent_key_matched = bool(runtime_intent_key and runtime_intent_key in intent_keys)
        exact_source_terms = self._exact_source_match_terms(mapping, runtime_signature)
        source_overlap = [token for token in runtime_signature["source_terms"] if token in source_terms]
        context_overlap = [token for token in runtime_signature["context_terms"] if token in context_terms]
        page_overlap = [token for token in runtime_signature["page_terms"] if token in page_terms]
        role_overlap = [token for token in runtime_role_terms if token in target_role_terms]
        segment_overlap = [token for token in runtime_segment_terms if token in segment_terms]
        chain_overlap = [token for token in runtime_chain_terms if token in action_chain_terms]
        expected_overlap = [token for token in runtime_expected_terms if token in expected_terms]
        locator_bonus = 0.0
        mapping_locator = str(match.get("locator_hint", "") or "").strip().lower()
        runtime_locator = str(runtime_signature.get("locator_hint", "") or "").strip().lower()
        if (
            mapping_locator
            and runtime_locator
            and mapping_locator != runtime_locator
            and not intent_key_matched
            and not exact_source_terms
        ):
            return 0.0, []
        if mapping_locator and mapping_locator == runtime_locator:
            locator_bonus = 0.01
        intent_recipe = mapping.get("intent_recipe", {})
        page_gate = intent_recipe.get("page_gate", {}) if isinstance(intent_recipe, dict) and isinstance(intent_recipe.get("page_gate", {}), dict) else {}
        required_page_terms = [str(item).strip().lower() for item in match.get("required_page_terms", []) if str(item).strip()]
        required_page_terms.extend(
            str(item).strip().lower() for item in page_gate.get("required_terms", []) if str(item).strip()
        )
        required_page_terms = self.unique(required_page_terms)
        forbidden_page_terms = [str(item).strip().lower() for item in match.get("forbidden_page_terms", []) if str(item).strip()]
        forbidden_page_terms.extend(
            str(item).strip().lower() for item in page_gate.get("forbidden_terms", []) if str(item).strip()
        )
        forbidden_page_terms = self.unique(forbidden_page_terms)
        page_blob = str(runtime_signature.get("page_blob", "") or "")
        if (
            (mapping_goal == "login" or mapping_business_action == "login_submit")
            and not any(
                self.term_present(term, page_blob)
                for term in ["plg_usr_login_name", "plg_usr_password", "plg_btn_login", "password"]
            )
        ):
            return 0.0, []
        if forbidden_page_terms and any(self.term_present(term, page_blob) for term in forbidden_page_terms):
            return 0.0, []
        if required_page_terms:
            required_hits = [term for term in required_page_terms if self.term_present(term, page_blob)]
            required_min_hits = 2 if len(required_page_terms) >= 3 else len(required_page_terms)
            if len(required_hits) < max(1, required_min_hits):
                return 0.0, []
        alias_score, alias_terms = self._best_source_signature_match(mapping, runtime_signature)
        semantic_overlap = segment_overlap or chain_overlap or expected_overlap
        if (
            not semantic_overlap
            and not source_overlap
            and not context_overlap
            and not page_overlap
            and not role_overlap
            and alias_score <= 0
            and not intent_key_matched
        ):
            return 0.0, []
        score = 0.0
        if intent_key_matched:
            score += 0.58
        if app_name:
            score += 0.22
        if suite_matches:
            score += 0.06
        if mapping_goal and mapping_goal == runtime_goal:
            score += 0.18
        if mapping_business_action and mapping_business_action == runtime_business_action:
            score += 0.12
        if mapping_action and mapping_action == runtime_signature["action_type"]:
            score += 0.04
        if mapping_family and (mapping_family == runtime_family or login_submit_family_compatible):
            score += 0.08
        score += min(0.38, 0.12 * len(segment_overlap))
        score += min(0.28, 0.07 * len(chain_overlap))
        score += min(0.14, 0.05 * len(expected_overlap))
        score += min(0.28, 0.07 * len(source_overlap))
        score += min(0.14, 0.035 * len(context_overlap))
        score += min(0.12, 0.03 * len(page_overlap))
        score += min(0.16, 0.08 * len(role_overlap))
        score += locator_bonus
        score += min(0.36, alias_score)
        intent_terms = [f"intent_key:{runtime_intent_key}"] if intent_key_matched else []
        return score, self.unique(
            intent_terms
            + segment_overlap
            + chain_overlap
            + expected_overlap
            + source_overlap
            + context_overlap
            + page_overlap
            + role_overlap
            + alias_terms
            + exact_source_terms
        )

    def _mapping_context_compatible(
        self,
        mapping: dict[str, Any],
        runtime_signature: dict[str, Any],
    ) -> bool:
        match = mapping.get("match", {})
        if not isinstance(match, dict):
            return False
        app_name = str(match.get("app_name", "") or "").strip().lower()
        runtime_app = str(runtime_signature.get("app_name", "") or "").strip().lower()
        if app_name and runtime_app and app_name != runtime_app:
            return False
        mapping_goal = str(match.get("business_goal", "") or "").strip().lower()
        runtime_goal = str(runtime_signature.get("business_goal", "") or "").strip().lower()
        if (
            mapping_goal
            and runtime_goal
            and mapping_goal not in {"generic", "navigate"}
            and runtime_goal not in {"generic", "navigate"}
            and mapping_goal != runtime_goal
        ):
            return False
        mapping_business_action = str(match.get("business_action", "") or "").strip().lower()
        runtime_business_action = str(runtime_signature.get("business_action", "") or "").strip().lower()
        if mapping_business_action and runtime_business_action and mapping_business_action != runtime_business_action:
            return False
        mapping_family = str(match.get("action_family", "") or "").strip().lower()
        runtime_family = str(runtime_signature.get("action_family", "") or "").strip().lower()
        login_submit_family_compatible = (
            mapping_business_action == "login_submit"
            and runtime_business_action == "login_submit"
            and mapping_family in {"click_family", "submit_family", "generic_family"}
            and runtime_family in {"click_family", "submit_family", "generic_family"}
        )
        if mapping_family and runtime_family and mapping_family != runtime_family and not login_submit_family_compatible:
            return False
        return True

    def _exact_source_match_terms(
        self,
        mapping: dict[str, Any],
        runtime_signature: dict[str, Any],
    ) -> list[str]:
        source_statement = str(runtime_signature.get("source_statement", "") or "").strip()
        locator_hint = str(runtime_signature.get("locator_hint", "") or "").strip()
        source_key = self.source_signature_key(runtime_signature)
        source_signatures = mapping.get("source_signatures", [])
        if not isinstance(source_signatures, list):
            return []
        for item in source_signatures:
            if not isinstance(item, dict):
                continue
            existing_statement = str(item.get("source_statement", "") or "").strip()
            existing_locator = str(item.get("locator_hint", "") or "").strip()
            existing_key = str(item.get("source_key", "") or "").strip()
            terms: list[str] = []
            if source_statement and existing_statement == source_statement:
                terms.append("exact_source_statement")
            if source_key and existing_key == source_key:
                terms.append("exact_source_key")
            if locator_hint and existing_locator and locator_hint == existing_locator:
                terms.append("exact_locator_hint")
            if "exact_source_statement" in terms or "exact_source_key" in terms:
                return terms
        return []

    def best_candidate(self, runtime_signature: dict[str, Any], min_score: float = 0.52) -> FulfillmentOption | None:
        mappings = self.cache.get("mappings", [])
        if not isinstance(mappings, list) or not mappings:
            return None
        runtime_intent_key = str(runtime_signature.get("intent_key", "") or self.intent_key(runtime_signature)).strip().lower()
        if runtime_intent_key:
            for mapping in mappings:
                if not isinstance(mapping, dict):
                    continue
                if self._mapping_failure_disabled(mapping):
                    continue
                if not self._mapping_context_compatible(mapping, runtime_signature):
                    continue
                if runtime_intent_key not in self.mapping_intent_keys(mapping):
                    continue
                score, matched_terms = self.match_mapping(mapping, runtime_signature)
                if score <= 0:
                    continue
                candidate = self.candidate_from_entry(mapping, runtime_signature, max(1.0, score), matched_terms)
                if candidate is not None:
                    candidate.metadata["intent_mapping_match_mode"] = "intent_key"
                    return candidate
        best_match: dict[str, Any] | None = None
        best_score = 0.0
        best_terms: list[str] = []
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            if self._mapping_failure_disabled(mapping):
                continue
            score, matched_terms = self.match_mapping(mapping, runtime_signature)
            if score > best_score:
                best_score = score
                best_match = mapping
                best_terms = matched_terms
        if best_match is None or best_score < min_score:
            return None
        return self.candidate_from_entry(best_match, runtime_signature, best_score, best_terms)

    def _mapping_failure_disabled(self, mapping: dict[str, Any]) -> bool:
        stats = mapping.get("stats", {}) if isinstance(mapping.get("stats"), dict) else {}
        failures = int(stats.get("failure_count", 0) or 0)
        successes = int(stats.get("success_count", 0) or 0)
        return failures >= 3 and failures > successes

    def update_stats(self, mapping_ids: list[str], field_name: str) -> bool:
        target_ids = {str(item).strip() for item in mapping_ids if str(item).strip()}
        if not target_ids:
            return False
        changed = False
        for mapping in self.cache.get("mappings", []):
            if not isinstance(mapping, dict):
                continue
            mapping_id = str(mapping.get("mapping_id", "") or "").strip()
            if mapping_id not in target_ids:
                continue
            stats = mapping.setdefault("stats", {})
            stats[field_name] = int(stats.get(field_name, 0) or 0) + 1
            if field_name == "hit_count":
                stats["last_matched_at"] = utc_now()
            if field_name == "success_count":
                stats["last_success_at"] = utc_now()
            if field_name == "failure_count":
                stats["last_failure_at"] = utc_now()
            target_recipes = mapping.get("target_recipes", [])
            if isinstance(target_recipes, list):
                for recipe in target_recipes:
                    if not isinstance(recipe, dict):
                        continue
                    recipe_stats = recipe.setdefault("stats", {})
                    recipe_stats[field_name] = int(recipe_stats.get(field_name, 0) or 0) + 1
                    if field_name == "hit_count":
                        recipe_stats["last_matched_at"] = utc_now()
                    if field_name == "success_count":
                        recipe_stats["last_success_at"] = utc_now()
                    if field_name == "failure_count":
                        recipe_stats["last_failure_at"] = utc_now()
            changed = True
        if changed:
            self.save(self.cache)
        return changed

    def mapping_has_source(
        self,
        mapping_id: str,
        source_key: str,
        source_statement: str = "",
        locator_hint: str = "",
    ) -> bool:
        mapping_id = str(mapping_id or "").strip()
        source_key = str(source_key or "").strip()
        source_statement = str(source_statement or "").strip()
        locator_hint = str(locator_hint or "").strip()
        if not mapping_id:
            return False
        mappings = self.cache.get("mappings", [])
        if not isinstance(mappings, list):
            return False
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            if str(mapping.get("mapping_id", "") or "").strip() != mapping_id:
                continue
            source_signatures = mapping.get("source_signatures", [])
            if not isinstance(source_signatures, list):
                return False
            for item in source_signatures:
                if not isinstance(item, dict):
                    continue
                if source_key and str(item.get("source_key", "") or "").strip() == source_key:
                    return True
                existing_statement = str(item.get("source_statement", "") or "").strip()
                existing_locator = str(item.get("locator_hint", "") or "").strip()
                if source_statement and existing_statement == source_statement:
                    return True
                if source_statement and existing_statement == source_statement and (
                    not locator_hint or not existing_locator or locator_hint == existing_locator
                ):
                    return True
            return False
        return False

    def upsert_success(
        self,
        runtime_signature: dict[str, Any],
        selector: str,
        action_type: str,
        selector_type: str,
        replay_value: str,
        patch_statement: str,
        expected_outcome: str,
        step_index: int,
        page_gate_text: str,
        reasoning: str,
        recipe_steps: list[dict[str, Any]] | None = None,
    ) -> None:
        mappings = self.cache.get("mappings", [])
        if not isinstance(mappings, list):
            mappings = []
            self.cache["mappings"] = mappings

        default_recipe_step = {
            "action_type": action_type,
            "selector": selector,
            "selector_type": selector_type,
            "value": str(replay_value or ""),
            "patch_statement": patch_statement,
            "expected_outcome": str(expected_outcome or ""),
            "explanation": f"Auto-learned from successful migration step {step_index}.",
        }
        learned_recipe_steps = [
            {**default_recipe_step, **step}
            for step in (recipe_steps or [default_recipe_step])
            if isinstance(step, dict)
        ]
        if not learned_recipe_steps:
            learned_recipe_steps = [default_recipe_step]
        active_recipe_id = self.recipe_id(learned_recipe_steps)
        source_payload = self.source_signature_payload(runtime_signature)
        runtime_source_key = str(source_payload.get("source_key", "") or "")

        existing_index = -1
        existing_reason = ""
        for index, existing in enumerate(mappings):
            if not isinstance(existing, dict):
                continue
            match = existing.get("match", {})
            if not isinstance(match, dict):
                continue
            same_app_family = (
                str(match.get("app_name", "") or "").strip().lower() == runtime_signature["app_name"]
                and str(match.get("business_goal", "") or "").strip().lower() == runtime_signature["business_goal"]
                and str(match.get("business_action", "") or runtime_signature["business_action"]).strip().lower()
                == runtime_signature["business_action"]
                and str(match.get("action_family", "") or "").strip().lower() == runtime_signature["action_family"]
            )
            if not same_app_family:
                continue
            target_recipes = existing.get("target_recipes", [])
            if isinstance(target_recipes, list) and any(
                isinstance(item, dict) and str(item.get("recipe_id", "") or "") == active_recipe_id
                for item in target_recipes
            ):
                existing_index = index
                existing_reason = "same_target_recipe"
                break
            if str(existing.get("recipe_id", "") or "") == active_recipe_id:
                existing_index = index
                existing_reason = "same_target_recipe"
                break
            source_signatures = existing.get("source_signatures", [])
            if isinstance(source_signatures, list) and any(
                isinstance(item, dict) and str(item.get("source_key", "") or "") == runtime_source_key
                for item in source_signatures
            ):
                existing_index = index
                existing_reason = "same_source_signature"
                break
            recipe = existing.get("recipe", {})
            existing_steps = recipe.get("steps", [])
            primary = (
                existing_steps[0]
                if isinstance(existing_steps, list) and existing_steps and isinstance(existing_steps[0], dict)
                else {}
            )
            existing_terms = [str(item).strip().lower() for item in match.get("source_terms", []) if str(item).strip()]
            term_overlap = [token for token in runtime_signature["source_terms"] if token in existing_terms]
            existing_role = str(match.get("target_role", "") or "").strip().lower()
            runtime_role = str(runtime_signature.get("target_role", "") or "").strip().lower()
            role_matches = bool(existing_role and runtime_role and existing_role == runtime_role)
            if (
                str(primary.get("action_type", "") or "").strip().lower() == action_type
                and (role_matches or str(primary.get("selector", "") or "").strip() == selector)
                and len(term_overlap) >= 2
            ):
                existing_index = index
                existing_reason = "legacy_similarity"
                break

        required_page_terms = self.page_gate_terms(page_gate_text, runtime_signature["business_goal"], selector)
        forbidden_page_terms = [
            term
            for term in ["forgotten", "register", "login problems", "password forgotten"]
            if term in str(reasoning or "").lower()
        ]
        target_role = str(runtime_signature.get("target_role", "") or "").strip()
        business_cues = self.unique(
            [str(item) for item in runtime_signature.get("business_cues", []) if str(item).strip()]
            + [str(item) for item in runtime_signature.get("segment_intent_terms", []) if str(item).strip()][:6]
            + [str(item) for item in runtime_signature.get("action_chain_terms", []) if str(item).strip()][:6]
            + runtime_signature["source_terms"][:4]
            + runtime_signature["context_terms"][:3]
        )[:14]
        oracle_cues = self.unique(
            [str(item) for item in runtime_signature.get("oracle_cues", []) if str(item).strip()]
            + [str(item) for item in runtime_signature.get("expected_terms", []) if str(item).strip()][:6]
            + ([str(expected_outcome)] if str(expected_outcome or "").strip() else [])
        )[:8]
        outcome_contract = str(expected_outcome or runtime_signature.get("expected_outcome", "") or "").strip()
        match_payload = {
            "app_name": runtime_signature["app_name"],
            "suite_name": "",
            "learned_suite_name": runtime_signature["suite_name"],
            "intent_key": runtime_signature.get("intent_key", "") or self.intent_key(runtime_signature),
            "intent_keys": [runtime_signature.get("intent_key", "") or self.intent_key(runtime_signature)],
            "business_goal": runtime_signature["business_goal"],
            "business_action": runtime_signature["business_action"],
            "action_type": runtime_signature["action_type"],
            "action_family": runtime_signature["action_family"],
            "intent_name": runtime_signature["intent_name"],
            "phase": str(runtime_signature.get("phase", "") or ""),
            "small_intention": str(runtime_signature.get("small_intention", "") or ""),
            "expected_result": str(runtime_signature.get("expected_result", "") or ""),
            "target_role": target_role,
            "target_role_terms": self.signal_terms(target_role, 8),
            "source_locator_hint": runtime_signature["locator_hint"],
            "locator_hint": runtime_signature["locator_hint"],
            "source_terms": runtime_signature["source_terms"],
            "context_terms": runtime_signature["context_terms"],
            "page_terms": runtime_signature["page_terms"],
            "segment_intent_terms": [
                str(item) for item in runtime_signature.get("segment_intent_terms", []) if str(item).strip()
            ][:18],
            "action_chain_terms": [
                str(item) for item in runtime_signature.get("action_chain_terms", []) if str(item).strip()
            ][:18],
            "expected_terms": [str(item) for item in runtime_signature.get("expected_terms", []) if str(item).strip()][:10],
            "required_page_terms": required_page_terms,
            "forbidden_page_terms": forbidden_page_terms,
        }
        recipe_payload = {
            "summary": (
                "Auto-learned target-side recipe for "
                f"{runtime_signature.get('phase') or runtime_signature['business_goal']} intention "
                f"'{runtime_signature.get('small_intention') or target_role or action_type}'."
            ),
            "steps": learned_recipe_steps,
        }
        target_recipe_payload = {
            "recipe_id": active_recipe_id,
            "summary": recipe_payload["summary"],
            "steps": learned_recipe_steps,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "learned_from_case": runtime_signature["case_id"],
            "cardinality_hint": "one_to_many" if len(learned_recipe_steps) > 1 else "one_to_one",
            "stats": {
                "learned_count": 1,
                "hit_count": 0,
                "success_count": 1,
                "last_learned_at": utc_now(),
                "last_success_at": utc_now(),
            },
        }
        intent_recipe_payload = {
            "summary": recipe_payload["summary"],
            "phase": str(runtime_signature.get("phase", "") or ""),
            "small_intention": str(runtime_signature.get("small_intention", "") or ""),
            "target_role": target_role,
            "action_family": runtime_signature["action_family"],
            "business_cues": business_cues,
            "oracle_cues": oracle_cues,
            "outcome_contract": outcome_contract,
            "page_gate": {
                "required_terms": required_page_terms,
                "forbidden_terms": forbidden_page_terms,
            },
            "binding": {
                "selector": selector,
                "selector_type": selector_type,
                "action_type": action_type,
                "value": str(replay_value or ""),
                "patch_statement": patch_statement,
            },
            "steps": learned_recipe_steps,
        }
        if existing_index >= 0:
            entry = mappings[existing_index]
            entry["match"] = self._merge_match_payload(
                entry.get("match", {}) if isinstance(entry.get("match", {}), dict) else {},
                match_payload,
            )
            entry["recipe_id"] = str(entry.get("recipe_id", "") or active_recipe_id)
            selected_recipe = self._upsert_target_recipe(entry, target_recipe_payload)
            entry["recipe"] = {
                "summary": str(selected_recipe.get("summary", "") or recipe_payload["summary"]),
                "steps": selected_recipe.get("steps", learned_recipe_steps),
            }
            entry["intent_recipe"] = {
                **intent_recipe_payload,
                "steps": selected_recipe.get("steps", learned_recipe_steps),
            }
            self._append_source_signature(entry, source_payload)
            entry["updated_at"] = utc_now()
            entry["cardinality"] = self.mapping_cardinality(
                entry,
                [step for step in entry.get("recipe", {}).get("steps", []) if isinstance(step, dict)],
            )
            entry.setdefault("merge_reasons", [])
            if isinstance(entry["merge_reasons"], list) and existing_reason:
                entry["merge_reasons"] = self.unique([str(item) for item in entry["merge_reasons"]] + [existing_reason])[:8]
            stats = entry.setdefault("stats", {})
            stats["learned_count"] = int(stats.get("learned_count", 0) or 0) + 1
            stats["success_count"] = int(stats.get("success_count", 0) or 0) + 1
            stats["last_learned_at"] = utc_now()
        else:
            slug_terms = runtime_signature["source_terms"][:3] or [
                runtime_signature["business_goal"],
                runtime_signature["action_family"],
            ]
            slug = "_".join(re.sub(r"[^a-z0-9]+", "_", term.lower()).strip("_") for term in slug_terms if term) or "mapping"
            mappings.append(
                {
                    "mapping_id": (
                        f"{runtime_signature['app_name'] or 'global'}_"
                        f"{runtime_signature['business_goal'] or 'generic'}_"
                        f"{runtime_signature['business_action'] or 'action'}_"
                        f"{runtime_signature['action_family'] or 'generic'}_{slug}"
                    ),
                    "recipe_id": active_recipe_id,
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                    "learned_from_case": runtime_signature["case_id"],
                    "cardinality": "one_to_many" if len(learned_recipe_steps) > 1 else "one_to_one",
                    "source_signatures": [source_payload],
                    "target_recipes": [target_recipe_payload],
                    "match": match_payload,
                    "intent_recipe": intent_recipe_payload,
                    "recipe": recipe_payload,
                    "stats": {
                        "learned_count": 1,
                        "hit_count": 0,
                        "success_count": 1,
                        "last_learned_at": utc_now(),
                        "last_success_at": utc_now(),
                    },
                }
            )
        self.save(self.cache)

    def _reject_bad_learned_recipe(
        self,
        runtime_signature: dict[str, Any],
        recipe_steps: list[dict[str, Any]],
    ) -> bool:
        business_action = str(runtime_signature.get("business_action", "") or "").strip().lower()
        source_blob = " ".join(
            [
                str(runtime_signature.get("source_statement", "") or ""),
                str(runtime_signature.get("locator_hint", "") or ""),
                " ".join(str(item) for item in runtime_signature.get("source_terms", [])),
                " ".join(str(item) for item in runtime_signature.get("context_terms", [])),
            ]
        ).lower()
        step_blob = " ".join(
            " ".join(
                [
                    str(step.get("action_type", "") or ""),
                    str(step.get("selector", "") or ""),
                    str(step.get("selector_type", "") or ""),
                    str(step.get("patch_statement", "") or ""),
                    str(step.get("explanation", "") or ""),
                ]
            )
            for step in recipe_steps
            if isinstance(step, dict)
        ).lower()
        return False
