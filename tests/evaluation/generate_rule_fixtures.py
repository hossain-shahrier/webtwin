#!/usr/bin/env python3
"""Generate minimal HTML fixtures from verified rules for clone regression."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "python" / "webtwin_core" / "src"))

os.environ.setdefault("WEBTWIN_STORE", "memory")


def _html_for_rule(rule: dict) -> str:
    condition = rule.get("condition", {})
    effect = rule.get("effect", {})
    trigger = condition.get("field", "trigger")
    effect_field = effect.get("field", "effect")
    trigger_value = condition.get("value", "")
    visible = effect.get("visible", True)
    display = "block" if visible else "none"
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Rule fixture {rule.get('name', trigger)}</title></head>
<body>
  <h1>Generated from verified rule</h1>
  <label>{trigger}
    <select id="{trigger}" name="{trigger}" onchange="document.getElementById('{effect_field}').style.display =
      this.value === '{trigger_value}' ? '{display}' : 'none'">
      <option value="">--</option>
      <option value="{trigger_value}">{trigger_value}</option>
      <option value="other">other</option>
    </select>
  </label>
  <div id="{effect_field}" name="{effect_field}" style="display:none">
    <label>{effect_field}<input name="{effect_field}" /></label>
  </div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate rule HTML fixtures from an investigation")
    parser.add_argument("--investigation-id", required=True)
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / "tests" / "evaluation" / "synthetic_ats" / "fixtures" / "generated"),
    )
    args = parser.parse_args()

    from api.services import investigations as svc
    from api.store import store

    inv_id = UUID(args.investigation_id)
    spec = svc.export_clone_spec(inv_id)
    verified = spec.get("behavior", {}).get("verified", [])
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {"investigation_id": args.investigation_id, "fixtures": []}
    for index, rule in enumerate(verified):
        name = rule.get("name", f"rule_{index}").replace(" ", "_").lower()[:48]
        path = out_dir / f"{name}.html"
        path.write_text(_html_for_rule(rule))
        manifest["fixtures"].append({"rule_id": rule.get("id"), "path": str(path.relative_to(ROOT))})

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {len(verified)} fixture(s) to {out_dir}")


if __name__ == "__main__":
    main()
