# tep-contributions — TEP Report / opt-in contribution intake (two doors, one corpus)

**[日本語](README.md) | English**

## What this is

This public repository receives opt-in contribution payloads built by
`grift contribute`. Submission is entirely voluntary; the CLI never sends
anything. **Intake has two doors; storage is a single public corpus:**

- **Public door (door: pr)**: you submit the payload as a PR yourself
  (optional credit via the `attribution` field)
- **Private door (door: private)**: after receiving your form/email
  submission, we open the PR on your behalf with a `door: private` manifest
  label (**your identity stays private**)

Both doors pass the same schema validation and land in the same corpus.

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

## Submitting via the public door

```bash
grift report                                     # 1) create a repo-scope report
grift contribute --out .grift/contribution.json  # 2) build & review the payload
# 3) PR the payload unchanged:
#    file: payloads/2026/<submission-id>.json
#    append one manifest.jsonl line: {"id":"...","sha256":"...","received_at":"...","door":"pr"}
#    optional credit: an `attribution` display name inside the payload (opt-in)
```

## The private door

Attach the payload file to the form (or the contact email below). We open the
PR on your behalf with `door: "private"` in the manifest. **Since you never
open the PR, your GitHub identity is never linked to the submission.**

## Mechanically enforced acceptance

CI runs on every PR (PRs containing identifying information **fail**):

- payload schema validation (`tep-contribution-v1`, repo scope only)
- **needle sweep**: email-shaped strings, `actors` arrays, paths, repo-name
  fields, any `@` character

**Never included**: canonical_id, actors, emails, paths, repo names (except
opt-in `attribution`), tenant-scope values.

## Inclusion in distributions

Follows the existing rules (MIN_N ≥ 30, immutable versioning).

---

## Contact (private door / withdrawals)

- Withdrawals & private submissions: `company@cor-jp.com`
- Questions: issues on this repository (Japanese / English)
