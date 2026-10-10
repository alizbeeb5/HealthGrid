"""Stateless, evidence-linked emergency suggestions using live reported context."""

import asyncio
from datetime import datetime
from time import monotonic

from app.modules.intelligence.advice_schemas import (
    AdviceEvidence,
    EmergencyAdviceProposal,
    EmergencyAdviceRequest,
    EmergencyAdviceResponse,
)
from app.modules.intelligence.config import IntelligenceSettings
from app.modules.intelligence.failures import failure_warning

WARNINGS = [
    "AI suggestions require review by the responsible emergency coordinator.",
    "Modeled capacity is not spare admission capacity. Occupancy, transfer eligibility, "
    "transport availability and travel times are not supplied; resource moves are unverified.",
    "Draft incident details are unconfirmed assumptions. Guidance does not change reports, "
    "confirm incidents, dispatch resources or become a saved simulation.",
]


def evidence_value(context: dict, path: str):
    value = context
    for part in path.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    if isinstance(value, (list, dict)) or value == "":
        raise ValueError("Evidence must reference a supplied scalar value.")
    return value


async def emergency_advice(
    request: EmergencyAdviceRequest,
    context: dict,
    settings: IntelligenceSettings,
    now: datetime,
    provider=None,
) -> EmergencyAdviceResponse:
    start = monotonic()

    def response(status, proposal=None, evidence=None, warning=None, model=None):
        return EmergencyAdviceResponse(
            advice_status=status,
            proposal=proposal,
            evidence=evidence or [],
            warnings=[*WARNINGS, *([warning] if warning else [])],
            model=model or settings.openai_emergency_model,
            elapsed_ms=max(0, round((monotonic() - start) * 1000)),
            as_of=now,
        )

    if not settings.openai_api_key.get_secret_value() or provider is None:
        return response(
            "unavailable", warning="Emergency guidance is not configured on the server."
        )
    stage = "provider"
    try:
        async with asyncio.timeout(settings.openai_intelligence_timeout_seconds):
            result = await provider.advise(context, settings.openai_emergency_model)
        if any(
            part.type == "refusal"
            for item in result.output
            for part in getattr(item, "content", [])
        ):
            return response("refused", warning="The model declined this guidance request.")
        if result.status != "completed" or result.output_parsed is None:
            return response(
                "failed", warning="Guidance was incomplete. Try again or continue manually."
            )
        stage = "schema"
        proposal = EmergencyAdviceProposal.model_validate(result.output_parsed)
        stage = "evidence"
        evidence = {}
        for action in proposal.actions:
            if any(fid not in context["hospitals"] for fid in action.facility_ids):
                raise ValueError("Unknown hospital in guidance.")
            for path in action.evidence_paths:
                if path.split(".")[0] not in context:
                    raise ValueError("Invalid evidence source.")
                evidence[path] = AdviceEvidence(path=path, value=evidence_value(context, path))
        return response("completed", proposal, list(evidence.values()), model=result.model)
    except Exception as error:
        return response(
            "failed",
            warning=failure_warning(error, stage),
        )
