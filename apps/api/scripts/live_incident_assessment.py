"""Explicitly opt into one paid Decisions request using a fictional report.

Default execution is a preview. Never reads or writes the working database.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.modules.facilities.schemas import (  # noqa: E402
    FacilitySnapshotResponse,
    ResourceDefinition,
)
from app.modules.intelligence.adapter import openai_provider  # noqa: E402
from app.modules.intelligence.catalog import ReportCatalog  # noqa: E402
from app.modules.intelligence.config import IntelligenceSettings  # noqa: E402
from app.modules.intelligence.service import assess_report  # noqa: E402

ROOT = API_ROOT.parents[1]


def demo_inputs():
    examples = ROOT / "contracts/examples/feature-1"
    cases = json.loads((ROOT / "data/synthetic/feature-5/report-cases.json").read_text())
    report = next(case["report_text"] for case in cases if case["case"] == "clear-outage")
    catalog = ReportCatalog(
        snapshots=tuple(
            FacilitySnapshotResponse.model_validate(
                json.loads((examples / f"DEMO-{letter}.snapshot.response.json").read_text())
            )
            for letter in "ABC"
        ),
        resources=tuple(
            ResourceDefinition.model_validate(row)
            for row in json.loads((examples / "resource-definitions.json").read_text())
        ),
    )
    return report, catalog


async def live_assessment(report, catalog, settings):
    async with openai_provider(settings) as provider:
        return await assess_report(report, catalog, settings, provider)


def main():
    parser = argparse.ArgumentParser(description="Preview or run one live fictional assessment.")
    parser.add_argument("--live", action="store_true", help="Send one paid OpenAI Decisions call.")
    arguments = parser.parse_args()
    settings = IntelligenceSettings()
    report, catalog = demo_inputs()
    if not arguments.live:
        print(
            json.dumps(
                {
                    "mode": "preview",
                    "model": settings.openai_assessment_model,
                    "report_text": report,
                    "provider_request_sent": False,
                },
                indent=2,
            )
        )
        return 0
    if not settings.openai_api_key.get_secret_value():
        print(
            "No server OPENAI_API_KEY configured. Set it in the root .env, then rerun --live.",
            file=sys.stderr,
        )
        return 2
    try:
        result = asyncio.run(live_assessment(report, catalog, settings))
    except Exception:
        print(
            "Provider initialization failed. Check server configuration; key details are hidden.",
            file=sys.stderr,
        )
        return 1
    print(result.model_dump_json(indent=2))
    return 0 if result.assessment_status in {"completed", "refused"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
