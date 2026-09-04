#!/usr/bin/env python3
"""Generate manifest.jsonl from payloads/**.meta.json.

The file is derived, git-ignored, and never committed: CI runs this on every
event and publishes the result as the `manifest` artifact. A committed copy
would need a bot push to main, which the organization ruleset rejects
(2026-09-04, run 33900740283).
"""

from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    rows = []
    for meta_path in sorted(Path("payloads").rglob("*.meta.json")):
        row = json.loads(meta_path.read_text(encoding="utf-8"))
        rows.append(json.dumps(row, ensure_ascii=False))
    Path("manifest.jsonl").write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
    print(f"manifest.jsonl: {len(rows)} row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
