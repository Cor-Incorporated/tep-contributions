#!/usr/bin/env python3
"""Validate contribution PRs: v1 + v2 public-profile schema + no-private rails.

Enforces (ruling 2026-08-23, two-doors/one-corpus intake; extended 2026-08-31
for tep-contribution-v2 public profiles; hardened 2026-08-31 review):
- payload lives at payloads/<year>/<submission-id>.json
- v1: schema/purpose/scope checks + needle sweep (emails, actors arrays,
  paths, repo-name fields, any '@')
- v2: privacy_profile must be a PUBLIC profile (aggregate / named-public) and
  door must be public-pr. masked/raw are controlled-study artifacts and are
  a hard error at this intake until a controlled destination is authorized.
- v2 transformation_spec_digest must equal the digest emitted by the grift
  CLI (single embedded constant, cross-checked by grift-cli-dev CI against
  src/tep_core/contribution_v2.py).
- v2 measurement sections, field keys, bucket labels, coverage sources,
  missingness reasons, and text enums are validated against the closed
  allowlists mirrored from the CLI transformer. Raw numbers are rejected:
  the public profile carries buckets only, never exact counts.
- Any key from the forbidden-judgment vocabulary (score, rank, fit, hire,
  verdict, ...) is rejected at every depth of a v2 payload.
- named-public may carry provider-neutral project/account references, but
  raw emails, git OIDs (40/64-hex), actor rows, and unknown keys still fail.
- manifest.jsonl has exactly one matching line per payload
  (id, sha256, received_at ISO, door in {pr, private})

Exits non-zero on any violation (PRs with identifying information fail CI).
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import quote, unquote_plus, urlsplit, urlunsplit

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
V2_NAMED_PUBLIC_DATA = {
    "project",
    "authority",
    "actors",
    "measurements",
    "coverage",
    "missingness",
}
V2_PROJECT_KEYS = {"provider", "host", "project_id", "project_path"}
V2_AUTHORITY_KEYS = {"accounts"}
V2_AUTHORITY_ACCOUNT_KEYS = {
    "provider",
    "host",
    "project_id",
    "account_id",
    "basis",
    "scope",
    "assertion",
}
V2_ACCOUNT_KEYS = {
    "provider",
    "host",
    "account_id",
    "handle",
    "profile_url",
    "evidence",
}
V2_ACCOUNT_EVIDENCE_KEYS = {"basis", "coverage_status", "account_match_status"}
V2_ACTOR_KEYS = {"account", "measurements"}
V2_ACTOR_MEASUREMENT_KEYS = {
    "linked_commit_count_bucket",
    "actor_commit_count_bucket",
    "linkage_coverage_bucket",
    "commit_count_basis",
}
FORBIDDEN_KEYS = {
    "canonical_id",
    "actor",
    "actors",
    "emails",
    "path",
    "repo",
    "repository",
    "name",
}
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
# Review hardening: judgment vocabulary must never enter the corpus, at any
# depth. Same family as grift-cli scripts/check_forbidden_vocab.py.
FORBIDDEN_JUDGMENT_KEYS = {
    "score",
    "scores",
    "rank",
    "ranking",
    "fit",
    "fitness",
    "hire",
    "hiring",
    "verdict",
    "recommendation",
    "recommendations",
    "overall",
    "rating",
    "grade",
    "percentile",
    "percentile_rank",
    "seniority",
    "reputation",
    "reputation_score",
    "quality_score",
    "competence",
    "productivity_score",
    "performance",
    "badge",
}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PATHLIKE_RE = re.compile(r"(^|[\s\"'])(/[\w.-]+){2,}|([A-Za-z]:\\\\)")
HEX40_RE = re.compile(r"\b[0-9a-f]{40}\b")
HEX64_RE = re.compile(r"\b[0-9a-f]{64}\b")
RECEIPT_RE = re.compile(r"^receipt_[a-z2-7]{26}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RECEIVED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
SAFE_PROVIDER_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
SAFE_ACCOUNT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
SAFE_HANDLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SAFE_PROJECT_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,127}$")
PARAMETER_KEY_RE = re.compile(r"(?:^|[?&#;])([^=&#;\s]{1,120})=")
HIGH_CONFIDENCE_TOKEN_RE = re.compile(
    r"(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"glpat-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|"
    r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"
)

# ---------------------------------------------------------------------------
# Closed allowlists mirrored from grift-cli src/tep_core/contribution_v2.py.
# grift-cli-dev CI verifies these constants still match the CLI (see
# .github/workflows/ci.yml "intake-contract-parity" job). Update both sides
# in one coordinated change; a silent drift fails that job.
# ---------------------------------------------------------------------------
TRANSFORMATION_SPEC_DIGESTS = {
    "aggregate": "sha256:559265d4d765abb19de629329c3424d3b2fdb633fe45abbe9d964b651f3f5d04",
    "named-public": "sha256:d6f759617a832b2ca7bf4a12e7808d44ca6e5d38ab9b2f406048e3e5bb207baa",
}
SOURCE_REPLAY_BY_PROFILE = {
    "aggregate": "unavailable_from_public_payload",
    "named-public": "public_api_recollect_required",
}
NAMED_AUTHORITY_BASIS = "account_holder_explicit"
NAMED_AUTHORITY_SCOPE = "project_and_account"
NAMED_AUTHORITY_ASSERTION = "authorized_for_public_research_contribution"
PUBLIC_ACCOUNT_EVIDENCE_BASES = {
    "commit.author.id",
    "commit_sha_to_account",
    "provider_commit_account",
}
PUBLIC_ACCOUNT_COVERAGE = {"complete", "partial"}
NAMED_COMMIT_COUNT_BASIS = "git_primary_author_cluster_including_merges"
MEASUREMENT_SECTIONS = frozenset(
    {
        "activity",
        "attribution",
        "change_rhythm",
        "context_profile",
        "coordination_profile",
        "event_observation",
        "event_rhythm",
        "experience",
        "role_lens",
        "role_profile",
        "surface_profile",
        "tracker_lifecycle",
        "verification_profile",
    }
)
AGGREGATE_COVERAGE_SOURCES = frozenset(
    {
        "event_window",
        "forge",
        "forge_tracker_window_alignment",
        "git",
        "git_window",
        "public_forge",
        "report",
        "tracker",
        "tracker_window",
        "window_alignment",
    }
)
MISSINGNESS_KINDS = frozenset(
    {"not_observed", "not_proven", "not_declared", "suppressed"}
)
MISSINGNESS_PATHS = MEASUREMENT_SECTIONS | {"input_coverage"}
COVERAGE_KINDS = frozenset({"observed", "not_observed", "not_proven"})
COUNT_BUCKETS = frozenset({"0", "1-4", "5-19", "20-99", "100-499", "500-1999", "2000+"})
RATIO_BUCKETS = frozenset(f"{i:02d}-{i + 10:02d}%" for i in range(0, 100, 10))
BUCKET_VALUES = COUNT_BUCKETS | RATIO_BUCKETS
TEXT_ENUMS = {
    "kind": frozenset(
        {
            "declared",
            "directional",
            "display_preset",
            "mixed",
            "not_comparable",
            "not_declared",
            "not_observed",
            "not_proven",
            "observed",
            "suppressed",
        }
    ),
    "unit": frozenset(
        {
            "boolean",
            "commit-pairs",
            "commit_share",
            "commits",
            "coverage_status",
            "date-range",
            "days",
            "dimensionless",
            "events",
            "file-changes",
            "files",
            "hours",
            "input",
            "label",
            "lens",
            "lines",
            "month-range",
            "path_touch_share",
            "profile",
            "ratio",
            "surface",
            "target_commits",
            "utc_date_range",
            "verification-type",
        }
    ),
    "status": frozenset(
        {
            "complete",
            "insufficient_population",
            "not_available",
            "not_observed",
            "not_proven",
            "partial",
            "unknown",
            "unsupported",
        }
    ),
    "classification_basis": frozenset({"path_pattern_and_extension_heuristic"}),
    "window_basis": frozenset({"explicit_as_of", "fixed_oid", "legacy_head_date"}),
    "analysis_scope": frozenset({"repo"}),
    "fixture_kind": frozenset({"synthetic_contract"}),
}
with (Path(__file__).resolve().parent / "intake_allowlists.json").open(
    "r", encoding="utf-8"
) as _allowlist_file:
    _ALLOWLISTS = json.load(_allowlist_file)
AGGREGATE_FIELD_KEYS = frozenset(_ALLOWLISTS["aggregate_field_keys"])
AGGREGATE_VALUE_LABELS = frozenset(_ALLOWLISTS["value_labels"])
AGGREGATE_REASONS = frozenset(_ALLOWLISTS["reasons"])
if _ALLOWLISTS.get("transformation_spec_digests") != TRANSFORMATION_SPEC_DIGESTS:
    raise RuntimeError("intake allowlist profile digests drifted from validator")
if _ALLOWLISTS.get("source_replay_by_profile") != SOURCE_REPLAY_BY_PROFILE:
    raise RuntimeError("intake allowlist source-replay policy drifted from validator")
_named_allowlist = _ALLOWLISTS.get("named_public")
if not isinstance(_named_allowlist, dict) or _named_allowlist != {
    "authority_basis": NAMED_AUTHORITY_BASIS,
    "authority_scope": NAMED_AUTHORITY_SCOPE,
    "authority_assertion": NAMED_AUTHORITY_ASSERTION,
    "account_evidence_bases": sorted(PUBLIC_ACCOUNT_EVIDENCE_BASES),
    "coverage_statuses": sorted(PUBLIC_ACCOUNT_COVERAGE),
    "commit_count_basis": NAMED_COMMIT_COUNT_BASIS,
    "max_accounts": 1,
}:
    raise RuntimeError("intake allowlist named-public contract drifted from validator")


_FAILURES: list[str] = []


class DuplicateKeyError(ValueError):
    """Raised when JSON would otherwise silently overwrite a duplicate key."""


def _object_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value!r}")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON number {value!r}")
    return parsed


def _loads_strict(raw: str) -> object:
    """Load standards-compliant JSON without lossy duplicate-key handling."""

    return json.loads(
        raw,
        object_pairs_hook=_object_no_duplicates,
        parse_constant=_reject_non_finite,
        parse_float=_parse_finite_float,
    )


def fail(msg: str) -> None:
    _FAILURES.append(msg)


def _is_str(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _decoded_variants(value: str) -> Iterable[str]:
    """Yield the original text and a bounded set of percent-decoded forms."""

    candidate = value
    yield candidate
    for _ in range(3):
        decoded = unquote_plus(candidate)
        if decoded == candidate:
            return
        yield decoded
        candidate = decoded


def _credential_field_name(value: object) -> bool:
    raw = str(value)
    split_acronyms = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", raw)
    split_camel = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", split_acronyms)
    words = {
        re.sub(r"\d+$", "", word.lower())
        for word in re.findall(r"[A-Za-z0-9]+", split_camel)
    }
    credential_words = {
        "authorization",
        "auth",
        "cookie",
        "credential",
        "credentials",
        "csrf",
        "jwt",
        "key",
        "oauth",
        "passcode",
        "passphrase",
        "passwd",
        "password",
        "pat",
        "pwd",
        "secret",
        "session",
        "token",
    }
    if words & credential_words:
        return True
    collapsed = "".join(words)
    return (
        any(
            marker in collapsed
            for marker in (
                "authorization",
                "authcode",
                "credential",
                "password",
                "passphrase",
                "privatekey",
                "secret",
                "sessiontoken",
                "token",
            )
        )
        or collapsed.startswith(
            (
                "accesskey",
                "apikey",
                "authkey",
                "clientsecret",
                "keymaterial",
                "oauth",
                "privatekey",
            )
        )
        or collapsed.endswith(
            (
                "accesskey",
                "apikey",
                "authkey",
                "cookie",
                "credential",
                "password",
                "privatekey",
                "secret",
                "token",
            )
        )
    )


def _contains_credential_parameter(value: str) -> bool:
    return any(
        _credential_field_name(match.group(1))
        for candidate in _decoded_variants(value)
        for match in PARAMETER_KEY_RE.finditer(candidate)
    )


def _safe_public_text(value: object, *, allow_url: bool = False) -> bool:
    if not _is_str(value):
        return False
    text = str(value)
    if _contains_credential_parameter(text):
        return False
    for candidate in _decoded_variants(text):
        if EMAIL_RE.search(candidate) or "@" in candidate:
            return False
        if not allow_url and (
            "http://" in candidate.lower() or "https://" in candidate.lower()
        ):
            return False
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in candidate):
            return False
    return True


def _valid_host(value: object) -> bool:
    if not isinstance(value, str) or not value or value != value.lower():
        return False
    if (
        any(character in value for character in "/@?#\\")
        or any(character.isspace() for character in value)
        or value.startswith(("http://", "https://"))
    ):
        return False
    try:
        parsed = urlsplit("//" + value)
        _ = parsed.port
    except ValueError:
        return False
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.netloc != value
    ):
        return False
    hostname = parsed.hostname
    try:
        if ":" in hostname:
            canonical_hostname = f"[{ipaddress.IPv6Address(hostname).compressed}]"
        elif re.fullmatch(r"[0-9.]+", hostname):
            canonical_hostname = str(ipaddress.IPv4Address(hostname))
        else:
            labels = hostname.split(".")
            if len(hostname) > 253 or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in labels
            ):
                return False
            canonical_hostname = hostname
    except ipaddress.AddressValueError:
        return False
    canonical = canonical_hostname
    if parsed.port is not None:
        canonical += f":{parsed.port}"
    return value == canonical


def _safe_project_id(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 255:
        return False
    if (
        "@" in value
        or any(character.isspace() or ord(character) < 0x20 for character in value)
        or _contains_credential_parameter(value)
        or HIGH_CONFIDENCE_TOKEN_RE.search(value)
    ):
        return False
    has_scheme = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value) is not None
    return not has_scheme or value.startswith("gid://")


def _safe_project_path(value: object) -> bool:
    if not isinstance(value, str):
        return False
    segments = value.split("/")
    return len(segments) >= 2 and all(
        SAFE_PROJECT_PATH_SEGMENT_RE.fullmatch(segment) for segment in segments
    )


def _safe_profile_url(value: object, host: object, handle: object) -> bool:
    if (
        not _safe_public_text(value, allow_url=True)
        or not _valid_host(host)
        or not isinstance(handle, str)
        or not SAFE_HANDLE_RE.fullmatch(handle)
    ):
        return False
    expected_host = str(host)
    expected_url = f"https://{expected_host}/{quote(handle, safe='')}"
    for candidate in _decoded_variants(str(value)):
        try:
            parsed = urlsplit(candidate)
            expected = urlsplit("//" + expected_host)
            actual_port = parsed.port
            expected_port = expected.port
        except ValueError:
            return False
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or (parsed.hostname or "").lower() != (expected.hostname or "").lower()
            or actual_port != expected_port
            or expected_port == 443
            or parsed.netloc != expected_host
            or candidate != expected_url
            or candidate != urlunsplit(("https", expected_host, parsed.path, "", ""))
        ):
            return False
    return True


def _validate_measurement_tree(node: object, label: str, prefix: str) -> None:
    """Closed-shape walk over bucketed measurement data.

    Everything numeric must already be a bucket string; raw numbers, lists,
    unregistered keys, and judgment vocabulary are rejected.
    """

    if not isinstance(node, dict):
        fail(f"{label}: unsupported measurement node at {prefix}")
        return
    for raw_key, value in node.items():
        key = str(raw_key)
        where = f"{prefix}.{key}" if prefix else key
        lowered = key.lower()
        if lowered in FORBIDDEN_JUDGMENT_KEYS:
            fail(f"{label}: forbidden judgment key {key!r} at {where}")
            continue
        if lowered in FORBIDDEN_KEYS_V2:
            fail(f"{label}: forbidden key {key!r} at {where}")
            continue
        if key == "value_buckets":
            _validate_value_buckets(value, label, where)
            continue
        if key.endswith("_bucket"):
            # The transformer emits <registered_field>_bucket dynamically;
            # the base field must still be registered and the value a bucket.
            base = key[: -len("_bucket")]
            if base != "value" and base not in AGGREGATE_FIELD_KEYS:
                fail(f"{label}: unregistered measurement field {key!r} at {where}")
                continue
            if not isinstance(value, str) or value not in BUCKET_VALUES:
                fail(f"{label}: unregistered bucket label {value!r} at {where}")
            continue
        if key not in AGGREGATE_FIELD_KEYS:
            fail(f"{label}: unregistered measurement field {key!r} at {where}")
            continue
        if isinstance(value, bool):
            if key not in {"provided", "narrate_rate"}:
                fail(f"{label}: boolean is not allowed at {where}")
            continue
        if isinstance(value, (int, float)):
            fail(f"{label}: raw number at {where}; public profiles carry buckets only")
            continue
        if isinstance(value, list):
            fail(f"{label}: array at {where}; arrays are omitted by the transformer")
            continue
        if isinstance(value, str):
            if key in TEXT_ENUMS:
                if value not in TEXT_ENUMS[key]:
                    fail(f"{label}: unregistered {key} value {value!r} at {where}")
                continue
            fail(
                f"{label}: free-form string at {where} is not produced by the transformer"
            )
            continue
        _validate_measurement_tree(value, label, where)


def _validate_value_buckets(node: object, label: str, prefix: str) -> None:
    if not isinstance(node, dict) or not node:
        fail(f"{label}: value_buckets must be a non-empty object at {prefix}")
        return
    for raw_label, bucket in node.items():
        label_text = str(raw_label)
        if label_text not in AGGREGATE_VALUE_LABELS:
            fail(f"{label}: unregistered value-bucket label {label_text!r} at {prefix}")
            continue
        if bucket not in BUCKET_VALUES:
            fail(f"{label}: unregistered bucket {bucket!r} at {prefix}.{label_text}")


def _validate_aggregate_measurements(node: object, label: str) -> None:
    if not isinstance(node, dict) or not node:
        fail(f"{label}: measurements must be a non-empty object")
        return
    for section, body in node.items():
        if section not in MEASUREMENT_SECTIONS:
            fail(f"{label}: unregistered measurement section {section!r}")
            continue
        _validate_measurement_tree(body, label, str(section))


def _validate_aggregate_coverage(node: object, label: str) -> None:
    if not isinstance(node, dict) or not node:
        fail(f"{label}: coverage must be a non-empty object")
        return
    for source, body in node.items():
        if source not in AGGREGATE_COVERAGE_SOURCES:
            fail(f"{label}: unregistered coverage source {source!r}")
            continue
        if not isinstance(body, dict) or set(body) - {"kind", "provided", "reason"}:
            fail(f"{label}: coverage.{source} keys are outside the closed shape")
            continue
        if "kind" in body and body["kind"] not in COVERAGE_KINDS:
            fail(f"{label}: coverage.{source}.kind is not a closed enum value")
        if "provided" in body and not isinstance(body["provided"], bool):
            fail(f"{label}: coverage.{source}.provided must be a boolean")
        if "reason" in body and body["reason"] not in AGGREGATE_REASONS:
            fail(f"{label}: coverage.{source}.reason is not a registered reason")


def _validate_aggregate_missingness(node: object, label: str) -> None:
    if not isinstance(node, list):
        fail(f"{label}: missingness must be an array")
        return
    for index, row in enumerate(node):
        where = f"{label}: missingness[{index}]"
        if not isinstance(row, dict) or set(row) != {"path", "kind", "reason"}:
            fail(f"{where}: must have exactly path/kind/reason")
            continue
        if row["path"] not in MISSINGNESS_PATHS:
            fail(f"{where}: unregistered path {row['path']!r}")
        if row["kind"] not in MISSINGNESS_KINDS:
            fail(f"{where}: unregistered kind {row['kind']!r}")
        if row["reason"] not in AGGREGATE_REASONS:
            fail(f"{where}: unregistered reason {row['reason']!r}")


def _validate_aggregate_population(node: object, label: str) -> None:
    if not isinstance(node, dict) or set(node) != {"n_bucket", "denominator_bucket"}:
        fail(f"{label}: population must have exactly n_bucket/denominator_bucket")
        return
    for key, value in node.items():
        if value not in BUCKET_VALUES:
            fail(f"{label}: population.{key} is not a registered bucket")


def _validate_judgment_free(node: object, label: str, prefix: str = "") -> None:
    """Reject judgment vocabulary and identity keys at every depth.

    ``path``/``kind``/``reason`` are structurally validated inside the closed
    measurement/missingness walkers, so only their VALUE vocabulary matters
    here; the judgment sweep still applies to their contents.
    """

    if isinstance(node, dict):
        for raw_key, value in node.items():
            key = str(raw_key)
            where = f"{prefix}.{key}" if prefix else key
            lowered = key.lower()
            if lowered in FORBIDDEN_JUDGMENT_KEYS:
                fail(f"{label}: forbidden judgment key {key!r} at {where}")
            elif lowered in FORBIDDEN_KEYS_V2 and key != "path":
                fail(f"{label}: forbidden key {key!r} at {where}")
            _validate_judgment_free(value, label, where)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _validate_judgment_free(item, label, f"{prefix}[{index}]")


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
    expected_digest = TRANSFORMATION_SPEC_DIGESTS.get(str(profile))
    if digest != expected_digest:
        fail(
            f"{label}: transformation_spec_digest must equal the {profile!r} "
            "digest emitted by the grift CLI transformer"
        )
    policy = payload.get("policy")
    if not isinstance(policy, dict) or set(policy) != V2_POLICY_KEYS:
        fail(f"{label}: policy keys are outside the closed v2 policy shape")
    elif (
        policy.get("public_payload") is not True
        or policy.get("access_class") != "public"
        or policy.get("source_replay") != SOURCE_REPLAY_BY_PROFILE[profile]
    ):
        fail(
            f"{label}: v2 public policy must use access_class=public, "
            f"public_payload=true, source_replay={SOURCE_REPLAY_BY_PROFILE[profile]}"
        )
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
            return
        _validate_aggregate_population(data.get("population"), label)
    else:
        if set(data) != V2_NAMED_PUBLIC_DATA:
            fail(
                f"{label}: named-public data keys must be exactly {sorted(V2_NAMED_PUBLIC_DATA)}"
            )
            return
        _validate_named_public(data, label)
    _validate_aggregate_measurements(data.get("measurements"), label)
    _validate_aggregate_coverage(data.get("coverage"), label)
    _validate_aggregate_missingness(data.get("missingness"), label)
    _validate_judgment_free(payload, label)

    # Global leak sweep for v2: emails anywhere, git-object-shaped hex outside
    # the registered transformation digest, and unregistered URL positions.
    text = json.dumps(payload, ensure_ascii=False)
    if EMAIL_RE.search(text) or "@" in text:
        fail(f"{label}: email-shaped string present")
    if PATHLIKE_RE.search(text):
        fail(f"{label}: path-like string present")
    if isinstance(digest, str):
        swept = text.replace(digest, "")
        if digest.startswith("sha256:"):
            swept = swept.replace(digest[len("sha256:") :], "")
    else:
        swept = text
    if HEX40_RE.search(swept) or HEX64_RE.search(swept):
        fail(
            f"{label}: git-object-shaped hex string present outside the registered digest"
        )


def _validate_named_public(data: dict, label: str) -> None:
    project = data.get("project")
    if not isinstance(project, dict) or set(project) != V2_PROJECT_KEYS:
        fail(
            f"{label}: named-public project must have exactly {sorted(V2_PROJECT_KEYS)}"
        )
        project = {}
    else:
        if not isinstance(
            project.get("provider"), str
        ) or not SAFE_PROVIDER_RE.fullmatch(str(project.get("provider"))):
            fail(f"{label}: named-public project.provider is not canonical")
        if not _valid_host(project.get("host")):
            fail(f"{label}: named-public project.host is not canonical")
        if not _safe_project_id(project.get("project_id")):
            fail(f"{label}: named-public project.project_id is not canonical")
        if not _safe_project_path(project.get("project_path")):
            fail(f"{label}: named-public project.project_path is not canonical")
    authority = data.get("authority")
    if not isinstance(authority, dict) or set(authority) != V2_AUTHORITY_KEYS:
        fail(
            f"{label}: named-public authority must contain only "
            f"{sorted(V2_AUTHORITY_KEYS)}"
        )
        authority_rows: object = None
    else:
        authority_rows = authority.get("accounts")
    authority_bindings: set[tuple[str, str, str]] = set()
    if not isinstance(authority_rows, list) or len(authority_rows) != 1:
        fail(
            f"{label}: named-public authority.accounts must contain exactly one account"
        )
    else:
        for index, row in enumerate(authority_rows):
            where = f"{label}: authority.accounts[{index}]"
            if not isinstance(row, dict) or set(row) != V2_AUTHORITY_ACCOUNT_KEYS:
                fail(f"{where}: fields are outside the closed authority account shape")
                continue
            binding = (
                str(row.get("provider")),
                str(row.get("host")),
                str(row.get("account_id")),
            )
            if binding in authority_bindings:
                fail(f"{where}: duplicate authority account binding")
            authority_bindings.add(binding)
            if (
                row.get("provider") != project.get("provider")
                or row.get("host") != project.get("host")
                or row.get("project_id") != project.get("project_id")
            ):
                fail(f"{where}: authority binding does not match project")
            if not SAFE_ACCOUNT_ID_RE.fullmatch(
                str(row.get("account_id", ""))
            ) or HIGH_CONFIDENCE_TOKEN_RE.search(str(row.get("account_id", ""))):
                fail(f"{where}: account_id is not canonical")
            if str(row.get("account_id", "")).startswith("legacy-login:"):
                fail(f"{where}: legacy login is not a stable account id")
            if (
                row.get("basis") != NAMED_AUTHORITY_BASIS
                or row.get("scope") != NAMED_AUTHORITY_SCOPE
                or row.get("assertion") != NAMED_AUTHORITY_ASSERTION
            ):
                fail(f"{where}: authority vocabulary is not registered")
    actors = data.get("actors")
    if not isinstance(actors, list) or len(actors) != 1:
        fail(f"{label}: named-public actors must contain exactly one account-bound row")
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
        if not isinstance(
            account.get("provider"), str
        ) or not SAFE_PROVIDER_RE.fullmatch(str(account.get("provider"))):
            fail(f"{where}: account.provider must be canonical")
        if not _valid_host(account.get("host")):
            fail(f"{where}: account.host must be canonical")
        if not isinstance(
            account.get("account_id"), str
        ) or not SAFE_ACCOUNT_ID_RE.fullmatch(str(account.get("account_id"))):
            fail(f"{where}: account.account_id must be a stable public id")
        elif HIGH_CONFIDENCE_TOKEN_RE.search(str(account.get("account_id"))):
            fail(f"{where}: account.account_id resembles credential material")
        if str(account.get("account_id", "")).startswith("legacy-login:"):
            fail(f"{where}: legacy login is not a stable account id")
        if not isinstance(account.get("handle"), str) or not SAFE_HANDLE_RE.fullmatch(
            str(account.get("handle"))
        ):
            fail(f"{where}: account.handle must be canonical display text")
        profile_url = account.get("profile_url")
        host = account.get("host")
        handle = account.get("handle")
        if not _safe_profile_url(profile_url, host, handle):
            fail(f"{where}: account.profile_url must be the canonical profile URL")
        identity = (
            str(account.get("provider")),
            str(host),
            str(account.get("account_id")),
        )
        if identity in seen_accounts:
            fail(f"{where}: duplicate provider/host/account_id entry")
        seen_accounts.add(identity)
        if account.get("provider") != project.get("provider") or account.get(
            "host"
        ) != project.get("host"):
            fail(f"{where}: account provider/host does not match project")
        evidence = account.get("evidence")
        if not isinstance(evidence, dict) or set(evidence) != V2_ACCOUNT_EVIDENCE_KEYS:
            fail(f"{where}: account.evidence is outside the closed shape")
        elif (
            evidence.get("basis") not in PUBLIC_ACCOUNT_EVIDENCE_BASES
            or evidence.get("coverage_status") not in PUBLIC_ACCOUNT_COVERAGE
            or evidence.get("account_match_status") != "linked"
        ):
            fail(f"{where}: account.evidence vocabulary is not registered")
        if (
            not isinstance(measurements, dict)
            or set(measurements) != V2_ACTOR_MEASUREMENT_KEYS
        ):
            fail(f"{where}: actor measurements are outside the closed shape")
        else:
            for key in ("linked_commit_count_bucket", "actor_commit_count_bucket"):
                if measurements.get(key) not in COUNT_BUCKETS:
                    fail(f"{where}: {key} is not a registered count bucket")
            if measurements.get("linkage_coverage_bucket") not in RATIO_BUCKETS:
                fail(f"{where}: linkage_coverage_bucket is not a ratio bucket")
            if measurements.get("commit_count_basis") != NAMED_COMMIT_COUNT_BASIS:
                fail(f"{where}: commit_count_basis is not registered")
    if seen_accounts != authority_bindings:
        fail(f"{label}: authority accounts must exactly bind emitted actor accounts")


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
            continue
        try:
            row = _loads_strict(meta_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            fail(f"{meta_path}: invalid JSON ({exc})")
            continue
        if not isinstance(row, dict):
            fail(f"{meta_path}: metadata must be a JSON object")
            continue
        missing = sorted({"id", "sha256", "received_at", "door"} - set(row))
        if missing:
            fail(f"{meta_path}: missing keys {missing}")
            continue
        if row["door"] not in ("pr", "private"):
            fail(f"{meta_path}: door must be 'pr' or 'private'")
        if not RECEIVED_RE.match(str(row["received_at"])):
            fail(f"{meta_path}: received_at must be ISO datetime")
        manifest[row["id"]] = row
    # stale legacy manifest.jsonl (if present) must not contain ids missing
    # from the meta files — regeneration drift is itself a failure
    legacy = Path("manifest.jsonl")
    if legacy.is_file():
        for lineno, line in enumerate(
            legacy.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            try:
                row = _loads_strict(line)
            except ValueError as exc:
                fail(
                    f"manifest.jsonl:{lineno}: invalid JSON ({exc}) — regenerate on main"
                )
                continue
            if not isinstance(row, dict):
                fail(f"manifest.jsonl:{lineno}: row must be a JSON object")
                continue
            if row.get("id") not in manifest:
                fail(
                    f"manifest.jsonl:{lineno}: id {row.get('id')!r} has no payload/meta; regenerate on main"
                )

    for f in payloads:
        raw = f.read_text(encoding="utf-8")
        try:
            payload = _loads_strict(raw)
        except ValueError as exc:
            fail(f"{f}: invalid JSON ({exc})")
            continue
        if not isinstance(payload, dict):
            fail(f"{f}: contribution payload must be a JSON object")
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
                fail(
                    f"{f}: unexpected top-level keys {sorted(set(payload) - ALLOWED_TOP_V2)}"
                )
            _validate_v2(payload, str(f))
        elif schema == V1_SCHEMA:
            if payload.get("purpose") != V2_PURPOSE:
                fail(f"{f}: unexpected purpose")
            if set(payload) - ALLOWED_TOP_V1:
                fail(
                    f"{f}: unexpected top-level keys {sorted(set(payload) - ALLOWED_TOP_V1)}"
                )
            prov = payload.get("provenance") or {}
            if set(prov) - ALLOWED_PROV:
                fail(f"{f}: provenance has unexpected keys")
            if prov.get("analysis_scope") != "repo":
                fail(f"{f}: only repo-scope contributions are accepted")
            attribution = payload.get("attribution")
            if attribution is not None:
                if not isinstance(attribution, str) or len(attribution) > 64:
                    fail(f"{f}: attribution must be a display string <=64 chars")
                if (
                    EMAIL_RE.search(attribution)
                    or "http" in attribution
                    or "@" in attribution
                ):
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
                        if str(k).lower() in FORBIDDEN_JUDGMENT_KEYS:
                            fail(f"{f}: forbidden judgment key {k!r} at {prefix}")
                        walk(v, f"{prefix}.{k}" if prefix else k)
                elif isinstance(node, list):
                    for i, item in enumerate(node):
                        walk(item, f"{prefix}[{i}]")

            walk(payload)
        else:
            fail(f"{f}: contribution_schema must be {V1_SCHEMA} or {V2_SCHEMA}")
            continue
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
