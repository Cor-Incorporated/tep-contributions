from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.falsify_security import named_payload


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate.py"
FALSIFIER = ROOT / "scripts" / "falsify_security.py"
WORKFLOW = ROOT / ".github" / "workflows" / "validate.yml"
SCHEMA = ROOT / "schemas" / "tep-contribution-v2-public.schema.json"
PRODUCER_FIXTURES = ROOT / "tests" / "fixtures" / "grift-cli-v060-contract"


class ValidatorSecurityTests(unittest.TestCase):
    def run_intake(
        self, payload_raw: str, *, meta_raw: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload_dir = root / "payloads" / "2026"
            payload_dir.mkdir(parents=True)
            payload_path = payload_dir / "security-case.json"
            payload_path.write_text(payload_raw, encoding="utf-8")
            digest = hashlib.sha256(payload_path.read_bytes()).hexdigest()
            if meta_raw is None:
                meta_raw = json.dumps(
                    {
                        "id": "security-case",
                        "sha256": digest,
                        "received_at": "2026-08-31T00:00:00Z",
                        "door": "pr",
                    }
                )
            (payload_dir / "security-case.meta.json").write_text(
                meta_raw, encoding="utf-8"
            )
            return subprocess.run(
                [sys.executable, str(VALIDATOR)],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )

    def run_payload(
        self, payload: dict[str, object]
    ) -> subprocess.CompletedProcess[str]:
        return self.run_intake(json.dumps(payload, ensure_ascii=False))

    def test_valid_named_public_profile_still_passes(self) -> None:
        payload = named_payload()
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(payload)
        result = self.run_payload(payload)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_profile_url_rejects_userinfo_query_fragment_and_encoded_forms(
        self,
    ) -> None:
        urls = (
            "https://user:pass@github.com/example-handle",
            "https://user%3Apass%40github.com/example-handle",
            "https://github.com/example-handle?page=1",
            "https://github.com/example-handle#profile",
            "https://github.com/example-handle%3Faccess%255Ftoken%3Dopaque",
        )
        for url in urls:
            with self.subTest(url=url):
                payload = named_payload()
                payload["data"]["actors"][0]["account"]["profile_url"] = url
                result = self.run_payload(payload)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("account.profile_url", result.stdout)

    def test_encoded_credential_parameter_is_rejected_in_public_text(self) -> None:
        for credential in (
            "access%255Ftoken%3Dopaque",
            "accesstoken%3Dopaque",
            "clientSecret%3Dopaque",
        ):
            with self.subTest(credential=credential):
                payload = named_payload()
                payload["data"]["authority"]["accounts"][0]["assertion"] = credential
                result = self.run_payload(payload)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("authority vocabulary", result.stdout)

    def test_strict_json_rejects_duplicate_keys_and_non_finite_numbers(self) -> None:
        cases = (
            (
                '{"contribution_schema":"tep-contribution-v1",'
                '"contribution_schema":"tep-contribution-v2"}',
                "duplicate JSON key",
            ),
            (
                '{"contribution_schema":"tep-contribution-v1",'
                '"purpose":"TEP Report 集計と参照分布 vNext",'
                '"provenance":{"analysis_scope":"repo"},'
                '"metrics":{"value":NaN},"context_profile":{}}',
                "non-finite JSON number",
            ),
            (
                '{"contribution_schema":"tep-contribution-v1",'
                '"purpose":"TEP Report 集計と参照分布 vNext",'
                '"provenance":{"analysis_scope":"repo"},'
                '"metrics":{"value":1e10000},"context_profile":{}}',
                "non-finite JSON number",
            ),
        )
        for payload_raw, expected in cases:
            with self.subTest(expected=expected):
                result = self.run_intake(payload_raw)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(expected, result.stdout)

        valid_raw = json.dumps(named_payload(), ensure_ascii=False)
        duplicate_meta = (
            '{"id":"security-case","id":"shadowed",'
            '"sha256":"' + "0" * 64 + '",'
            '"received_at":"2026-08-31T00:00:00Z","door":"pr"}'
        )
        result = self.run_intake(valid_raw, meta_raw=duplicate_meta)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("duplicate JSON key", result.stdout)

    def test_security_falsifier_writes_deterministic_rejection_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "guard-ledger.jsonl"
            result = subprocess.run(
                [sys.executable, str(FALSIFIER), "--ledger", str(ledger)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            rows = [json.loads(line) for line in ledger.read_text().splitlines()]
        self.assertEqual(len(rows), 18)
        self.assertEqual(
            [row["case"] for row in rows], sorted(row["case"] for row in rows)
        )
        self.assertTrue(all(row["result"] == "rejected" for row in rows), rows)

    def test_one_sided_profile_url_guard_mutation_is_red(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "mutation-ledger.jsonl"
            result = subprocess.run(
                [
                    sys.executable,
                    str(FALSIFIER),
                    "--mutation-disable-profile-url-guard",
                    "--ledger",
                    str(ledger),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            row = json.loads(ledger.read_text().strip())
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(row["case"], "mutation-profile-url-guard-disabled")
        self.assertEqual(row["result"], "accepted")
        self.assertIn("UNSAFE ACCEPTANCE", result.stdout)

    def test_workflow_always_uploads_the_path_bound_guard_ledger(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for required in (
            "run: python scripts/falsify_security.py --ledger artifacts/guard-ledger.jsonl",
            "uses: actions/upload-artifact@v4",
            "name: intake-guard-ledger",
            "path: artifacts/guard-ledger.jsonl",
            "if-no-files-found: error",
        ):
            self.assertIn(required, workflow)
        self.assertGreaterEqual(workflow.count("if: always()"), 2)

    def test_rejection_messages_are_not_accidentally_duplicated(self) -> None:
        payload = named_payload()
        payload["data"]["actors"] = []
        result = self.run_payload(payload)
        self.assertEqual(
            result.stdout.count(
                "named-public actors must contain exactly one account-bound row"
            ),
            1,
            result.stdout,
        )

        payload = copy.deepcopy(named_payload())
        payload["privacy_profile"] = "aggregate"
        payload["data"] = {
            "population": {"n": 20, "denominator": 20},
            "measurements": {
                "surface_profile": {
                    "surface_commit_counts": {
                        "value_buckets": {"backend": "not-a-bucket"}
                    }
                }
            },
            "coverage": {"git": {"kind": "observed", "provided": True}},
            "missingness": [],
        }
        result = self.run_payload(payload)
        self.assertEqual(
            result.stdout.count("unregistered bucket 'not-a-bucket'"),
            1,
            result.stdout,
        )

    def test_exact_grift_cli_public_fixtures_pass_schema_and_intake(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for fixture_name in ("aggregate.json", "named-public.json"):
            with self.subTest(fixture=fixture_name):
                raw = (PRODUCER_FIXTURES / fixture_name).read_text(encoding="utf-8")
                payload = json.loads(raw)
                errors = sorted(
                    validator.iter_errors(payload), key=lambda error: list(error.path)
                )
                self.assertEqual(errors, [], [error.message for error in errors])
                result = self.run_intake(raw)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_aggregate_population_keeps_exact_closed_counts(self) -> None:
        base = json.loads((PRODUCER_FIXTURES / "aggregate.json").read_text())
        self.assertEqual(base["data"]["population"], {"n": 1, "denominator": 3})
        mutations = {
            "bucketed": {"n_bucket": "1-4", "denominator_bucket": "1-4"},
            "negative": {"n": -1, "denominator": 3},
            "boolean": {"n": True, "denominator": 3},
            "fractional": {"n": 1.5, "denominator": 3},
            "inverted": {"n": 4, "denominator": 3},
        }
        for name, population in mutations.items():
            with self.subTest(name=name):
                payload = copy.deepcopy(base)
                payload["data"]["population"] = population
                result = self.run_payload(payload)
                self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_profile_digest_and_source_replay_are_bound(self) -> None:
        fixture_names = ("aggregate.json", "named-public.json")
        for fixture_name in fixture_names:
            payload = json.loads((PRODUCER_FIXTURES / fixture_name).read_text())
            for field, value in (
                ("transformation_spec_digest", "sha256:" + "0" * 64),
                ("source_replay", "controlled_sidecar_available"),
            ):
                with self.subTest(fixture=fixture_name, field=field):
                    poisoned = copy.deepcopy(payload)
                    if field == "source_replay":
                        poisoned["policy"][field] = value
                    else:
                        poisoned[field] = value
                    result = self.run_payload(poisoned)
                    self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_named_public_binding_evidence_and_measurements_are_closed(self) -> None:
        base = json.loads((PRODUCER_FIXTURES / "named-public.json").read_text())
        mutations = {
            "authority-project": lambda payload: payload["data"]["authority"][
                "accounts"
            ][0].update({"project_id": "different"}),
            "authority-basis": lambda payload: payload["data"]["authority"]["accounts"][
                0
            ].update({"basis": "repository-owner"}),
            "evidence-missing": lambda payload: payload["data"]["actors"][0][
                "account"
            ].pop("evidence"),
            "evidence-unknown": lambda payload: payload["data"]["actors"][0]["account"][
                "evidence"
            ].update({"commit_oid": "opaque"}),
            "coverage-status": lambda payload: payload["data"]["actors"][0]["account"][
                "evidence"
            ].update({"coverage_status": "unknown"}),
            "raw-measurement": lambda payload: payload["data"]["actors"][0][
                "measurements"
            ].update({"linked_commit_count": 7}),
            "second-actor": lambda payload: payload["data"]["actors"].append(
                copy.deepcopy(payload["data"]["actors"][0])
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                payload = copy.deepcopy(base)
                mutate(payload)
                result = self.run_payload(payload)
                self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_controlled_profiles_are_hard_rejected_at_public_intake(self) -> None:
        base = json.loads((PRODUCER_FIXTURES / "aggregate.json").read_text())
        for profile in ("masked", "raw"):
            with self.subTest(profile=profile):
                payload = copy.deepcopy(base)
                payload["privacy_profile"] = profile
                result = self.run_payload(payload)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("controlled-study artifact", result.stdout)

    def test_gitlab_account_linkage_is_unsupported_even_with_matching_authority(
        self,
    ) -> None:
        payload = named_payload()
        payload["data"]["project"].update({"provider": "gitlab", "host": "gitlab.com"})
        payload["data"]["authority"]["accounts"][0].update(
            {"provider": "gitlab", "host": "gitlab.com"}
        )
        payload["data"]["actors"][0]["account"].update(
            {
                "provider": "gitlab",
                "host": "gitlab.com",
                "profile_url": "https://gitlab.com/example-handle",
                "evidence": {
                    "basis": "provider_commit_account",
                    "coverage_status": "complete",
                    "account_match_status": "linked",
                },
            }
        )
        result = self.run_payload(payload)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("account linkage is unsupported", result.stdout)


if __name__ == "__main__":
    unittest.main()
