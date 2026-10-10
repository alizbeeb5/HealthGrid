"""Export the live API schema without starting a server or opening a database."""

import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))
from app.main import app  # noqa: E402

output = API_ROOT.parents[1] / "contracts" / "openapi.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(app.openapi(), indent=2) + "\n")
print(f"Exported {output}")
