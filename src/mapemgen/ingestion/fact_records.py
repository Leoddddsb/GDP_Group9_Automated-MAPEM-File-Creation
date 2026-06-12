from __future__ import annotations

import hashlib
import json
from typing import Any


def make_fact(
    fact_name: str,
    value: Any,
    evidence_location: str,
    confidence: float,
    source_file: str | None = None,
) -> dict[str, Any]:
    fact = {
        "fact_name": fact_name,
        "payload": {"value": value},
        "evidence_location": evidence_location,
        "confidence": confidence,
    }
    if source_file is not None:
        fact["source_file"] = source_file
    fact["fact_id"] = stable_fact_id(fact)
    return fact


def with_evidence_prefix(fact: dict[str, Any], prefix: str) -> dict[str, Any]:
    item = dict(fact)
    item["evidence_location"] = f"{prefix} -> {fact['evidence_location']}"
    item["fact_id"] = stable_fact_id(item)
    return item


def with_source_file(fact: dict[str, Any], source_file: str) -> dict[str, Any]:
    item = dict(fact)
    item["source_file"] = source_file
    item["fact_id"] = stable_fact_id(item)
    return item


def stable_fact_id(fact: dict[str, Any]) -> str:
    identity = {
        "fact_name": fact.get("fact_name"),
        "payload": fact.get("payload"),
        "source_file": fact.get("source_file"),
        "evidence_location": fact.get("evidence_location"),
    }
    encoded = json.dumps(identity, sort_keys=True, ensure_ascii=False, default=str)
    return "fact_" + hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:12]
