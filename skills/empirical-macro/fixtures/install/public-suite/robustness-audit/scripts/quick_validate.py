import json
from pathlib import Path

valid = (Path(__file__).resolve().parents[1] / "SKILL.md").is_file()
print(json.dumps({"valid": valid}))
raise SystemExit(0 if valid else 1)
