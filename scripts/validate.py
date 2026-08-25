#!/usr/bin/env python3
"""Validate contribution PRs: tep-contribution-v1 schema + no-private rails.

Enforces (ruling 2026-08-23, two-doors/one-corpus intake):
- payload lives at payloads/<year>/<submission-id>.json
- schema/purpose/scope checks
- needle sweep: emails, actors arrays, paths, repo-name fields, any '@'
- optional attribution field (display name only; no emails/urls)
- manifest.jsonl has exactly one matching line per payload
  (id, sha256, received_at ISO, door in {pr, private})

Exits non-zero on any violation (PRs with identifying information fail CI).
"""

from __future__ import annotations

import hashlib
import json
import re
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
ALLOWED_TOP = {
    "contribution_schema",
    "purpose",
    "provenance",
    "metrics",
    "context_profile",
    "attribution",
}
FORBIDDEN_KEYS = {"canonical_id", "actor", "actors", "emails", "path", "repo", "repository", "name"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PATHLIKE_RE = re.compile(r"(^|[\s\"'])(/[\w.-]+){2,}|([A-Za-z]:\\\\)")
RECEIVED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


_FAILURES: list[str] = []


def fail(msg: str) -> None:
    _FAILURES.append(msg)


def main() -> int:
    # C (2026-08-25): PRs add payloads/<year>/<id>.json + <id>.meta.json only.
    # manifest.jsonl is GENERATED on main by CI from the meta files — parallel
    # PRs never conflict on a shared append target.
    payloads = sorted(p for p in Path("payloads").rglob("*.json") if not p.name.endswith(".meta.json"))
    if not payloads:
        fail("no payload JSON found under payloads/")
    manifest = {}
    for f in payloads:
        meta_path = f.parent / f"{f.stem}.meta.json"
        if not meta_path.is_file():
            fail(f"{f}: missing sidecar {f.stem}.meta.json")
        try:
            row = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(f"{meta_path}: invalid JSON ({exc})")
        for key in ("id", "sha256", "received_at", "door"):
            if key not in row:
                fail(f"{meta_path}: missing {key}")
        if row["door"] not in ("pr", "private"):
            fail(f"{meta_path}: door must be 'pr' or 'private'")
        if not RECEIVED_RE.match(str(row["received_at"])):
            fail(f"{meta_path}: received_at must be ISO datetime")
        manifest[row["id"]] = row
    # stale legacy manifest.jsonl (if present) must not contain ids missing
    # from the meta files — regeneration drift is itself a failure
    legacy = Path("manifest.jsonl")
    if legacy.is_file():
        for lineno, line in enumerate(legacy.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                fail(f"manifest.jsonl:{lineno}: invalid JSON ({exc}) — regenerate on main")
            if row.get("id") not in manifest:
                fail(f"manifest.jsonl:{lineno}: id {row.get('id')!r} has no payload/meta; regenerate on main")

    for f in payloads:
        raw = f.read_text(encoding="utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            fail(f"{f}: invalid JSON ({exc})")
        sub_id = f.stem
        if sub_id not in manifest:
            fail(f"{f}: no manifest.jsonl entry for id {sub_id!r}")
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if manifest[sub_id]["sha256"] != digest:
            fail(f"{f}: manifest sha256 mismatch (expected {digest[:16]}…)")
        if payload.get("contribution_schema") != "tep-contribution-v1":
            fail(f"{f}: contribution_schema must be tep-contribution-v1")
        if payload.get("purpose") != "TEP Report 集計と参照分布 vNext":
            fail(f"{f}: unexpected purpose")
        if set(payload) - ALLOWED_TOP:
            fail(f"{f}: unexpected top-level keys {sorted(set(payload) - ALLOWED_TOP)}")
        prov = payload.get("provenance") or {}
        if set(prov) - ALLOWED_PROV:
            fail(f"{f}: provenance has unexpected keys")
        if prov.get("analysis_scope") != "repo":
            fail(f"{f}: only repo-scope contributions are accepted")
        attribution = payload.get("attribution")
        if attribution is not None:
            if not isinstance(attribution, str) or len(attribution) > 64:
                fail(f"{f}: attribution must be a display string <=64 chars")
            if EMAIL_RE.search(attribution) or "http" in attribution or "@" in attribution:
                fail(f"{f}: attribution must not contain emails/urls/@")
        text = json.dumps(payload, ensure_ascii=False)
        if EMAIL_RE.search(text) or "@" in text:
            fail(f"{f}: email-shaped string present")
        if PATHLIKE_RE.search(text):
            fail(f"{f}: path-like string present")

        def walk(node, prefix=""):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k in FORBIDDEN_KEYS:
                        fail(f"{f}: forbidden key {k!r} at {prefix}")
                    walk(v, f"{prefix}.{k}" if prefix else k)
            elif isinstance(node, list):
                for i, item in enumerate(node):
                    walk(item, f"{prefix}[{i}]")

        walk(payload)
        if not _FAILURES:
            print(f"OK {f} (door={manifest[sub_id]['door']})")
    print(f"validated {len(payloads)} payload(s)")
    return 0


if __name__ == "__main__":
    code = main()
    if _FAILURES:
        for message in _FAILURES:
            print(f"VALIDATION FAIL: {message}")
        sys.exit(1)
    raise SystemExit(code)
