# tep-contributions — TEP Report / opt-in contribution intake (two doors, one corpus)

**[日本語](README.md) | English**

## What this is

This public repository receives opt-in contribution payloads built by
`grift contribute`. Submission is entirely voluntary; the CLI never sends
anything. **Intake has two doors; storage is a single public corpus:**

- **Public door (door: pr)**: you submit the payload as a PR yourself
  (optional credit via the `attribution` field)
- **Identity-private door (door: private)**: after receiving your form/email
  submission, we open the PR on your behalf with a `door: private` manifest
  label (**your identity stays private; the payload itself is eventually
  stored in this public corpus**)

Both doors pass the same schema validation and land in the same corpus.

## Submission profiles (tep-contribution-v2, from 2026-08-31)

`grift contribute --privacy` in v0.6.0+ emits four profiles, but **this
public intake accepts only the two public ones**:

| profile | accepted here | retained information |
|---|---|---|
| `aggregate` | yes (`public-pr` only) | bucketed measurements, exact n and denominator, coverage, missingness, and a random receipt id. No actor rows, repo/remote/OIDs, timestamps, or source digests. The public payload alone cannot replay or deduplicate the source |
| `named-public` | yes (`public-pr` only) | provider-neutral public project/account references and the author's actor observations. v0.6 accepts only GitHub's documented `commit.author.id` account linkage; GitLab repository observation remains supported while account linkage stays `unsupported/not_proven`. Requires explicit account-holder authority bound to the project/account and coverage. No raw emails, internal actor ids, or pseudonyms |
| `masked` | **no (hard error)** | high-fidelity observations with HMAC pseudonyms; requires a controlled-study sidecar |
| `raw` | **no (hard error)** | raw names/emails/OIDs; research-controlled path only |

`masked` and `raw` are controlled-study artifacts. Until a controlled
destination is authorized and provisioned, this intake rejects them
mechanically (CI fails). The intent is not to make raw data unobtainable but
to provision an explicit high-fidelity research path with a declared purpose
and access class.

## Purpose restriction

**Submitted data is used solely for "TEP Report aggregation and the next
reference distribution."** In particular, **reuse for channel 4 (Grift SaaS /
organization contracts) is forbidden**, including sales, estimation, and
business development use.

## Retention & withdrawal

- **The retention period (until the next annual Report) applies to the
  private door's identity records**
- **Payloads (the public corpus) are retained indefinitely unless withdrawn** —
  they stay public so third parties can recompute the reference distributions
  (verifiability)
- Withdrawal: (a) open a PR deleting your payload, or (b) contact the address
  at the bottom of this README (identities from the private door stay private)
- **Note**: because of Git history and forks, a payload once published can
  never be fully removed; withdrawal removes it from this repository's
  default view

## Submitting via the public door

```bash
grift report                                     # 1) create a repo-scope report
grift contribute --out .grift/contribution.json  # 2) build & review the payload
# 3) PR the payload unchanged:
#    file: payloads/2026/<submission-id>.json
#    add a sidecar <id>.meta.json in the same directory (manifest.jsonl is generated on main — do not edit): {"id":"...","sha256":"...","received_at":"...","door":"pr"}
#    optional credit: an `attribution` display name inside the payload (opt-in)
```

## The identity-private door

Attach the payload file to the form (or the contact email below). We open the
PR on your behalf with `door: "private"` in the manifest. **Since you never
open the PR, your GitHub identity is never linked to the submission.** Only
your identity record is private — **the payload itself is eventually stored
in this public corpus.**

## Mechanically enforced acceptance

CI runs on every PR (PRs containing identifying information **fail**):

- payload schema validation (`tep-contribution-v1` or the public profiles of
  `tep-contribution-v2`, repo scope only; v2 accepts `aggregate` and
  `named-public` only)
- profile-specific v2 transformation digests and source-replay contracts
  (`aggregate=unavailable_from_public_payload`,
  `named-public=public_api_recollect_required`)
- `named-public` currently accepts one stable account on one project and
  cross-checks closed `account_holder_explicit` / `project_and_account`
  authority, evidence, coverage, and actor buckets
- **needle sweep**: email-shaped strings, v1 `actors` arrays, paths,
  repo-name fields, any `@` character, git-OID-shaped (40/64 hex) strings
- v2 `named-public` URL/account references are limited to the closed
  provider/host/project/account shape (raw emails and controlled payloads
  are rejected)

**Included (with a note)**: v1 `metrics.provenance.analyzed_commit_sha` (the
commit SHA at analysis time) and `analyzed_at`. **The SHA is opaque — it
cannot restore content — but for public repositories it can identify the
target** (same caveat as the feature-combination re-identification risk).
The v2 `aggregate` profile does not carry this SHA.

**Never included**: canonical_id, actors (v1), emails, paths, repo names
(except opt-in `attribution`), tenant-scope values; for v2 additionally any
git OID.

An `aggregate` public payload cannot replay its source and is not sufficient
on its own to establish a reference distribution. `named-public` still
requires public-API recollection and coverage checks. CI validates the closed
receiver schema, fixtures emitted by the real CLI producer, and a
known-accident mutation ledger together.

## Inclusion in distributions

Follows the existing rules (MIN_N ≥ 30, immutable versioning).

---

## Contact (private door / withdrawals)

- Withdrawals & private submissions: `company@cor-jp.com`
- Questions: issues on this repository (Japanese / English)
