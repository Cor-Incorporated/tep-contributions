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


REAL_DIGEST = "sha256:42eb35f299c3d97490b459c590279b5a28e0790c393a6ac075f21e89e6b8f502"


def named_payload() -> dict[str, object]:
    return {
        "contribution_schema": "tep-contribution-v2",
        "privacy_profile": "named-public",
        "door": "public-pr",
        "purpose": "TEP Report 集計と参照分布 vNext",
        "provenance_receipt_id": "receipt_abcdefghijklmnopqrstuvwxyz",
        "transformation_spec_digest": REAL_DIGEST,
        "policy": {
            "access_class": "public",
            "public_payload": True,
            "source_replay": "controlled_sidecar_required",
        },
        "data": {
            "project": {
                "provider": "github",
                "host": "github.com",
                "project_id": "123456789",
                "project_path": "example/project",
            },
            "authority": {
                "basis": "provider-public-api",
                "scope": "account",
                "assertion": "stable numeric account id",
            },
            "actors": [
                {
                    "account": {
                        "provider": "github",
                        "host": "github.com",
                        "account_id": "12345678",
                        "handle": "example-handle",
                        "profile_url": "https://github.com/example-handle",
                    },
                    "measurements": {"commit_count_bucket": "20-99"},
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
    credential_text["data"]["authority"]["assertion"] = "access%255Ftoken%3Dopaque"
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
    return checks


def _mutation_check() -> list[tuple[str, Callable[[], list[str]]]]:
    payload = named_payload()
    payload["data"]["actors"][0]["account"]["profile_url"] = (
        "https://github.com/example-handle?access_token=opaque"
    )

    def disabled_guard() -> list[str]:
        original = validator._safe_profile_url
        validator._safe_profile_url = lambda _value, _host: True
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
