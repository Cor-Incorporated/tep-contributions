#!/usr/bin/env python3
"""Validate contribution PRs: v1 + v2 public-profile schema + no-private rails.

Enforces (ruling 2026-08-23, two-doors/one-corpus intake; extended 2026-08-31
for tep-contribution-v2 public profiles):
- payload lives at payloads/<year>/<submission-id>.json
- v1: schema/purpose/scope checks + needle sweep (emails, actors arrays,
  paths, repo-name fields, any '@')
- v2: privacy_profile must be a PUBLIC profile (aggregate / named-public) and
  door must be public-pr. masked/raw are controlled-study artifacts and are
  a hard error at this intake until a controlled destination is authorized.
  named-public may carry provider-neutral project/account references, but
  raw emails, git OIDs (40/64-hex), actor rows, and unknown keys still fail.
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
ALLOWED_TOP_V1 = {
    "contribution_schema",
    "purpose",
    "provenance",
    "metrics",
    "context_profile",
    "attribution",
}
V2_SCHEMA = "tep-contribution-v2"
V1_SCHEMA = "tep-contribution-v1"
V2_PURPOSE = "TEP Report 集計と参照分布 vNext"
ALLOWED_TOP_V2 = {
    "contribution_schema",
    "privacy_profile",
    "door",
    "purpose",
    "provenance_receipt_id",
    "transformation_spec_digest",
    "policy",
    "data",
}
V2_PUBLIC_PROFILES = {"aggregate", "named-public"}
V2_CONTROLLED_PROFILES = {"masked", "raw"}
V2_POLICY_KEYS = {"access_class", "public_payload", "source_replay"}
V2_AGGREGATE_DATA = {"population", "measurements", "coverage", "missingness"}
V2_NAMED_PUBLIC_DATA = {"project", "authority", "actors", "measurements", "coverage", "missingness"}
V2_PROJECT_KEYS = {"provider", "host", "project_id", "project_path"}
V2_AUTHORITY_KEYS = {"basis", "scope", "assertion"}
V2_ACCOUNT_KEYS = {"provider", "host", "account_id", "handle", "profile_url"}
V2_ACTOR_KEYS = {"account", "measurements"}
FORBIDDEN_KEYS = {"canonical_id", "actor", "actors", "emails", "path", "repo", "repository", "name"}
# In v2 the listed keys are structurally validated instead of blanket-banned:
# "actors"/"project*"/"account*" are checked against closed shapes below.
FORBIDDEN_KEYS_V2 = {
    "canonical_id",
    "emails",
    "path",
    "repo",
    "repository",
    "name",
    "remote",
    "oid",
}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PATHLIKE_RE = re.compile(r"(^|[\s\"'])(/[\w.-]+){2,}|([A-Za-z]:\\\\)")
HEX40_RE = re.compile(r"\b[0-9a-f]{40}\b")
HEX64_RE = re.compile(r"\b[0-9a-f]{64}\b")
RECEIPT_RE = re.compile(r"^receipt_[a-z2-7]{26}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RECEIVED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
SAFE_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


_FAILURES: list[str] = []


def fail(msg: str) -> None:
    _FAILURES.append(msg)


def _is_str(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _safe_public_text(value: object, *, allow_url: bool = False) -> bool:
    if not _is_str(value):
        return False
    text = str(value)
    if EMAIL_RE.search(text) or "@" in text:
        return False
    if not allow_url and ("http://" in text or "https://" in text):
        return False
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text):
        return False
    return True


def _validate_v2(payload: dict, label: str) -> None:
    profile = payload.get("privacy_profile")
    if profile in V2_CONTROLLED_PROFILES:
        fail(
            f"{label}: privacy_profile {profile!r} is a controlled-study artifact; "
            "this intake accepts only public profiles (aggregate, named-public)"
        )
        return
    if profile not in V2_PUBLIC_PROFILES:
        fail(f"{label}: v2 privacy_profile must be one of {sorted(V2_PUBLIC_PROFILES)}")
        return
    if payload.get("door") != "public-pr":
        fail(f"{label}: v2 payload door must be 'public-pr' at this intake")
    if payload.get("purpose") != V2_PURPOSE:
        fail(f"{label}: unexpected purpose")
    receipt = payload.get("provenance_receipt_id")
    if not _is_str(receipt) or not RECEIPT_RE.fullmatch(str(receipt)):
        fail(f"{label}: provenance_receipt_id must be an opaque receipt id")
    digest = payload.get("transformation_spec_digest")
    if not _is_str(digest) or not SHA256_RE.fullmatch(str(digest)):
        fail(f"{label}: transformation_spec_digest must be a sha256 hex digest")
    policy = payload.get("policy")
    if not isinstance(policy, dict) or set(policy) - V2_POLICY_KEYS:
        fail(f"{label}: policy keys are outside the closed v2 policy shape")
    elif policy.get("public_payload") is not True or policy.get("access_class") != "public":
        fail(f"{label}: v2 public intake requires policy.public_payload=true / access_class=public")
    data = payload.get("data")
    if not isinstance(data, dict):
        fail(f"{label}: v2 data must be an object")
        return
    if profile == "aggregate":
        if set(data) != V2_AGGREGATE_DATA:
            fail(
                f"{label}: aggregate data keys must be exactly "
                f"{sorted(V2_AGGREGATE_DATA)} (no actor rows, repo/remote/OIDs, timestamps)"
            )
    else:
        if set(data) != V2_NAMED_PUBLIC_DATA:
            fail(f"{label}: named-public data keys must be exactly {sorted(V2_NAMED_PUBLIC_DATA)}")
        _validate_named_public(data, label)

    # Global leak sweep for v2: emails anywhere, git-object-shaped hex outside
    # the registered transformation digest, and unregistered URL positions.
    text = json.dumps(payload, ensure_ascii=False)
    if EMAIL_RE.search(text) or "@" in text:
        fail(f"{label}: email-shaped string present")
    if PATHLIKE_RE.search(text):
        fail(f"{label}: path-like string present")
    swept = dict(payload)
    swept.pop("transformation_spec_digest", None)
    swept_text = json.dumps(swept, ensure_ascii=False)
    if HEX40_RE.search(swept_text) or HEX64_RE.search(swept_text):
        fail(f"{label}: git-object-shaped hex string present outside the registered digest")


def _validate_named_public(data: dict, label: str) -> None:
    project = data.get("project")
    if not isinstance(project, dict) or set(project) != V2_PROJECT_KEYS:
        fail(f"{label}: named-public project must have exactly {sorted(V2_PROJECT_KEYS)}")
    else:
        for key, value in project.items():
            if not _safe_public_text(value):
                fail(f"{label}: named-public project.{key} is not safe public text")
        if str(project.get("project_path", "")).startswith("/"):
            fail(f"{label}: named-public project_path must be relative, not absolute")
    authority = data.get("authority")
    if not isinstance(authority, dict) or not authority or set(authority) - V2_AUTHORITY_KEYS:
        fail(
            f"{label}: named-public authority must be a non-empty {sorted(V2_AUTHORITY_KEYS)} object"
        )
    else:
        for key, value in authority.items():
            if not _safe_public_text(value):
                fail(f"{label}: named-public authority.{key} is not safe public text")
    actors = data.get("actors")
    if not isinstance(actors, list) or not actors:
        fail(f"{label}: named-public actors must be a non-empty array")
        return
    seen_accounts: set[tuple[str, str, str]] = set()
    for index, actor in enumerate(actors):
        where = f"{label}: actors[{index}]"
        if not isinstance(actor, dict) or set(actor) != V2_ACTOR_KEYS:
            fail(f"{where}: must have exactly {sorted(V2_ACTOR_KEYS)}")
            continue
        account = actor.get("account")
        measurements = actor.get("measurements")
        if not isinstance(account, dict) or set(account) != V2_ACCOUNT_KEYS:
            fail(f"{where}: account must have exactly {sorted(V2_ACCOUNT_KEYS)}")
            continue
        for key in ("provider", "host", "account_id", "handle"):
            if not _is_str(account.get(key)) or not SAFE_TOKEN_RE.fullmatch(str(account.get(key))):
                fail(f"{where}: account.{key} must be a safe public token")
        profile_url = account.get("profile_url")
        host = str(account.get("host"))
        if (
            not _is_str(profile_url)
            or not str(profile_url).startswith(f"https://{host}/")
            or not _safe_public_text(profile_url, allow_url=True)
        ):
            fail(f"{where}: account.profile_url must be an https URL on the declared host")
        identity = (str(account.get("provider")), host, str(account.get("account_id")))
        if identity in seen_accounts:
            fail(f"{where}: duplicate provider/host/account_id entry")
        seen_accounts.add(identity)
        if not isinstance(measurements, dict) or set(measurements) - {"commit_count_bucket"}:
            fail(f"{where}: actor measurements must be limited to commit_count_bucket")


def main() -> int:
    # C (2026-08-25): PRs add payloads/<year>/<id>.json + <id>.meta.json only.
    # manifest.jsonl is GENERATED on main by CI from the meta files — parallel
    # PRs never conflict on a shared append target.
    payloads = sorted(
        p for p in Path("payloads").rglob("*.json") if not p.name.endswith(".meta.json")
    )
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
                fail(
                    f"manifest.jsonl:{lineno}: id {row.get('id')!r} has no payload/meta; regenerate on main"
                )

    for f in payloads:
        raw = f.read_text(encoding="utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            fail(f"{f}: invalid JSON ({exc})")
            continue
        sub_id = f.stem
        if sub_id not in manifest:
            fail(f"{f}: no manifest.jsonl entry for id {sub_id!r}")
            continue
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if manifest[sub_id]["sha256"] != digest:
            fail(f"{f}: manifest sha256 mismatch (expected {digest[:16]}…)")
        schema = payload.get("contribution_schema")
        if schema == V2_SCHEMA:
            if set(payload) - ALLOWED_TOP_V2:
                fail(f"{f}: unexpected top-level keys {sorted(set(payload) - ALLOWED_TOP_V2)}")
            _validate_v2(payload, str(f))
        elif schema == V1_SCHEMA:
            if payload.get("purpose") != V2_PURPOSE:
                fail(f"{f}: unexpected purpose")
            if set(payload) - ALLOWED_TOP_V1:
                fail(f"{f}: unexpected top-level keys {sorted(set(payload) - ALLOWED_TOP_V1)}")
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
        else:
            fail(f"{f}: contribution_schema must be {V1_SCHEMA} or {V2_SCHEMA}")
            continue

        # Shared closed-key walk for v2 (v1 keeps its own blanket rules above).
        if schema == V2_SCHEMA:

            def walk_v2(node, prefix=""):
                if isinstance(node, dict):
                    for k, v in node.items():
                        if k in FORBIDDEN_KEYS_V2:
                            fail(f"{f}: forbidden key {k!r} at {prefix}")
                        walk_v2(v, f"{prefix}.{k}" if prefix else k)
                elif isinstance(node, list):
                    for i, item in enumerate(node):
                        walk_v2(item, f"{prefix}[{i}]")

            walk_v2(payload)
        if not _FAILURES:
            print(f"OK {f} (door={manifest[sub_id]['door']}, schema={schema})")
    print(f"validated {len(payloads)} payload(s)")
    return 0


if __name__ == "__main__":
    code = main()
    if _FAILURES:
        for message in _FAILURES:
            print(f"VALIDATION FAIL: {message}")
        sys.exit(1)
    raise SystemExit(code)
