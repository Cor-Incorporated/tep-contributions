#!/usr/bin/env python3
"""Record known security-boundary mutations against the public intake guard."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Callable

try:
    from scripts import validate as validator
except ModuleNotFoundError:
    import validate as validator  # type: ignore[no-redef]


NAMED_DIGEST = "sha256:d6f759617a832b2ca7bf4a12e7808d44ca6e5d38ab9b2f406048e3e5bb207baa"


def named_payload() -> dict[str, object]:
    return {
        "contribution_schema": "tep-contribution-v2",
        "privacy_profile": "named-public",
        "door": "public-pr",
        "purpose": "TEP Report 集計と参照分布 vNext",
        "provenance_receipt_id": "receipt_abcdefghijklmnopqrstuvwxyz",
        "transformation_spec_digest": NAMED_DIGEST,
        "policy": {
            "access_class": "public",
            "public_payload": True,
            "source_replay": "public_api_recollect_required",
        },
        "data": {
            "project": {
                "provider": "github",
                "host": "github.com",
                "project_id": "123456789",
                "project_path": "example/project",
            },
            "authority": {
                "accounts": [
                    {
                        "provider": "github",
                        "host": "github.com",
                        "project_id": "123456789",
                        "account_id": "12345678",
                        "basis": "account_holder_explicit",
                        "scope": "project_and_account",
                        "assertion": "authorized_for_public_research_contribution",
                    }
                ]
            },
            "actors": [
                {
                    "account": {
                        "provider": "github",
                        "host": "github.com",
                        "account_id": "12345678",
                        "handle": "example-handle",
                        "profile_url": "https://github.com/example-handle",
                        "evidence": {
                            "basis": "commit.author.id",
                            "coverage_status": "complete",
                            "account_match_status": "linked",
                        },
                    },
                    "measurements": {
                        "linked_commit_count_bucket": "20-99",
                        "actor_commit_count_bucket": "20-99",
                        "linkage_coverage_bucket": "90-100%",
                        "commit_count_basis": (
                            "git_primary_author_cluster_including_merges"
                        ),
                    },
                }
            ],
            "measurements": {"attribution": {"commit_count_bucket": "20-99"}},
            "coverage": {"git": {"kind": "observed", "provided": True}},
            "missingness": [],
        },
    }


def _payload_failures(payload: dict[str, object]) -> list[str]:
    validator._FAILURES.clear()
    validator._validate_v2(payload, "security-falsifier")
    return sorted(set(validator._FAILURES))


def _strict_json_failures(raw: str) -> list[str]:
    try:
        validator._loads_strict(raw)
    except ValueError as exc:
        return [str(exc)]
    return []


def _known_accidents() -> list[tuple[str, Callable[[], list[str]]]]:
    checks: list[tuple[str, Callable[[], list[str]]]] = []
    for name, url in (
        ("profile-url-userinfo", "https://user:pass@github.com/example-handle"),
        (
            "profile-url-encoded-userinfo",
            "https://user%3Apass%40github.com/example-handle",
        ),
        ("profile-url-query", "https://github.com/example-handle?page=1"),
        ("profile-url-fragment", "https://github.com/example-handle#profile"),
        (
            "profile-url-encoded-query",
            "https://github.com/example-handle%3Faccess%255Ftoken%3Dopaque",
        ),
    ):
        payload = named_payload()
        payload["data"]["actors"][0]["account"]["profile_url"] = url
        checks.append((name, lambda payload=payload: _payload_failures(payload)))

    credential_text = named_payload()
    credential_text["data"]["authority"]["accounts"][0]["assertion"] = (
        "access%255Ftoken%3Dopaque"
    )
    checks.append(
        (
            "encoded-credential-parameter",
            lambda: _payload_failures(credential_text),
        )
    )
    checks.extend(
        (
            (
                "duplicate-json-key",
                lambda: _strict_json_failures('{"door":"pr","door":"private"}'),
            ),
            (
                "non-finite-json-number",
                lambda: _strict_json_failures('{"value":NaN}'),
            ),
        )
    )
    for name, mutate in (
        (
            "wrong-profile-digest",
            lambda payload: payload.update(
                {"transformation_spec_digest": "sha256:" + "0" * 64}
            ),
        ),
        (
            "wrong-source-replay",
            lambda payload: payload["policy"].update(
                {"source_replay": "unavailable_from_public_payload"}
            ),
        ),
        (
            "authority-project-mismatch",
            lambda payload: payload["data"]["authority"]["accounts"][0].update(
                {"project_id": "different-project"}
            ),
        ),
        (
            "missing-account-evidence",
            lambda payload: payload["data"]["actors"][0]["account"].pop("evidence"),
        ),
        (
            "unknown-account-evidence-key",
            lambda payload: payload["data"]["actors"][0]["account"]["evidence"].update(
                {"commit_oid": "opaque"}
            ),
        ),
        (
            "raw-actor-measurement",
            lambda payload: payload["data"]["actors"][0]["measurements"].update(
                {"linked_commit_count": 24}
            ),
        ),
        (
            "unauthorized-second-actor",
            lambda payload: payload["data"]["actors"].append(
                copy.deepcopy(payload["data"]["actors"][0])
            ),
        ),
    ):
        payload = named_payload()
        mutate(payload)
        checks.append((name, lambda payload=payload: _payload_failures(payload)))
    for profile in ("masked", "raw"):
        payload = named_payload()
        payload["privacy_profile"] = profile
        checks.append(
            (
                f"controlled-profile-{profile}",
                lambda payload=payload: _payload_failures(payload),
            )
        )
    return checks


def _mutation_check() -> list[tuple[str, Callable[[], list[str]]]]:
    payload = named_payload()
    payload["data"]["actors"][0]["account"]["profile_url"] = (
        "https://github.com/example-handle?access_token=opaque"
    )

    def disabled_guard() -> list[str]:
        original = validator._safe_profile_url
        validator._safe_profile_url = lambda _value, _host, _handle: True
        try:
            return _payload_failures(copy.deepcopy(payload))
        finally:
            validator._safe_profile_url = original

    return [("mutation-profile-url-guard-disabled", disabled_guard)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("artifacts/guard-ledger.jsonl"),
    )
    parser.add_argument("--mutation-disable-profile-url-guard", action="store_true")
    args = parser.parse_args(argv)

    checks = (
        _mutation_check()
        if args.mutation_disable_profile_url_guard
        else _known_accidents()
    )
    rows: list[dict[str, object]] = []
    accepted: list[str] = []
    for case, check in sorted(checks, key=lambda item: item[0]):
        failures = check()
        rejected = bool(failures)
        rows.append(
            {
                "case": case,
                "expected": "rejected",
                "failure_count": len(failures),
                "failures": failures,
                "result": "rejected" if rejected else "accepted",
            }
        )
        if not rejected:
            accepted.append(case)

    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    args.ledger.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        ),
        encoding="utf-8",
    )
    print(f"falsified {len(rows)} security cases; accepted={len(accepted)}")
    print(f"ledger: {args.ledger}")
    if accepted:
        print("UNSAFE ACCEPTANCE: " + ", ".join(accepted))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
