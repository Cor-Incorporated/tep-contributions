# grift-contributions — TEP Report / opt-in contribution intake

**[日本語](README.md) | English**

## What this is

This public repository receives opt-in contribution payloads built by
`grift contribute`. Submission is entirely voluntary; the CLI never sends
anything — you review the payload and open the PR yourself.

## How to submit

```bash
# 1. Create a repo-scope report in the target repository
grift report                      # → .grift/report.{json,md}

# 2. Build the payload (the full text is printed and the flow states that
#    "this submission will appear in a public repository")
grift contribute --out .grift/contribution.json

# 3. Review the payload, then open a PR to this repository
#    File name: contributions/YYYY/MMDD-HHMM-<hash8>.json
#    (e.g. contributions/2026/0823-1415-a1b2c3d4.json)
#    The payload never contains repo names, emails, canonical_ids, or paths.
```

## Accepted / not accepted

**Accepted**: repo-scope aggregate values + context_profile (class-level
fields) + definition versions — a single `tep-contribution-v1` JSON file.

**Never included (excluded by rule)**: canonical_id, actors, emails, paths,
repo name (unless you choose to add it), tenant-scope values.

## How submissions are used

- Use is limited to "TEP Report aggregation and the next reference
  distribution" — nothing else
- Retained until the next annual Report; withdrawal accepted via issue (or
  a revert PR)
- See the retention section of the
  [grift-cli norms](https://github.com/Cor-Incorporated/grift-cli/blob/main/docs/norms.md)

## Review

- Schema validation (`tep-contribution-v1`) is performed mechanically
- **PRs containing personally identifiable content or off-schema data are rejected**
- Inclusion in distributions follows the existing rules (MIN_N ≥ 30, immutable versioning)
