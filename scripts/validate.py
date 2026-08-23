#!/usr/bin/env python3
"""Validate contribution PRs: tep-contribution-v1 schema + no-private rails."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ALLOWED_PROV = {
    "tool_name",
    "tool_version",
    "definition_version",
    "origin_definition_version",
    "activity_definition_version",
    "analysis_scope",
}
FORBIDDEN_KEYS = {"canonical_id", "actor", "actors", "emails", "path"}


def fail(msg: str) -> None:
    print(f"VALIDATION FAIL: {msg}")
    sys.exit(1)


def main() -> int:
    files = sorted(Path("contributions").rglob("*.json"))
    if not files:
        fail("no contribution JSON found in contributions/")
    for f in files:
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(f"{f}: invalid JSON ({exc})")
        if payload.get("contribution_schema") != "tep-contribution-v1":
            fail(f"{f}: contribution_schema must be tep-contribution-v1")
        if payload.get("purpose") != "TEP Report 集計と参照分布 vNext":
            fail(f"{f}: unexpected purpose")
        prov = payload.get("provenance") or {}
        if set(prov) - ALLOWED_PROV:
            fail(f"{f}: provenance has unexpected keys")
        if prov.get("analysis_scope") != "repo":
            fail(f"{f}: only repo-scope contributions are accepted")
        text = json.dumps(payload, ensure_ascii=False)
        if "@" in text:
            fail(f"{f}: email-shaped string present")
        for key in FORBIDDEN_KEYS:
            if f'"{key}"' in text:
                fail(f"{f}: forbidden key {key!r}")
        print(f"OK {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
