"""Independent stateless AI component calls; never save or confirm an incident."""

import asyncio
from time import monotonic

from pydantic import BaseModel

from app.modules.intelligence.adapter import QUESTIONS, RUBRIC_VERSION
from app.modules.intelligence.catalog import ReportCatalog
from app.modules.intelligence.config import IntelligenceSettings
from app.modules.intelligence.schemas import (
    AssessmentResponse,
    ExtractionProposal,
    ExtractionResponse,
    ReportRequest,
    ReviewAnswer,
)
from app.modules.intelligence.validation import validate_proposal


def _elapsed(start: float) -> int:
    return max(0, round((monotonic() - start) * 1000))


async def assess_report(
    report_text: str,
    catalog: ReportCatalog,
    settings: IntelligenceSettings,
    provider=None,
) -> AssessmentResponse:
    ReportRequest(report_text=report_text)
    start = monotonic()
    model = settings.openai_assessment_model
    if not settings.openai_api_key.get_secret_value() or provider is None:
        return AssessmentResponse(
            assessment_status="unavailable",
            answers=[],
            model=model,
            rubric_version=RUBRIC_VERSION,
            elapsed_ms=_elapsed(start),
        )
    try:
        async with asyncio.timeout(settings.openai_intelligence_timeout_seconds):
            result = await provider.assess(report_text, catalog, model)
        answers = []
        for answer in result.answers:
            if answer.type == "refusal":
                answers.append(ReviewAnswer(name=answer.name, value=None, answer_status="refused"))
            elif answer.type == "choice":
                answers.append(
                    ReviewAnswer(name=answer.name, value=answer.choice, answer_status="completed")
                )
            else:
                raise ValueError("Unexpected Decisions answer type.")
        # Stable rubric order, not provider response order; missing/extra/duplicate
        # answers are rejected by the response contract, never filled in locally.
        answers.sort(key=lambda row: list(QUESTIONS).index(row.name))
        status = "refused" if all(a.answer_status == "refused" for a in answers) else "completed"
        return AssessmentResponse(
            assessment_status=status,
            answers=answers,
            model=result.model,
            rubric_version=RUBRIC_VERSION,
            elapsed_ms=_elapsed(start),
        )
    except Exception:
        # Provider details may contain report text or credentials. Do not log or
        # return them; timeout, malformed output and transport failure stay failed.
        return AssessmentResponse(
            assessment_status="failed",
            answers=[],
            model=model,
            rubric_version=RUBRIC_VERSION,
            elapsed_ms=_elapsed(start),
        )


async def extract_report(
    report_text: str,
    catalog: ReportCatalog,
    candidate_model: type[BaseModel],
    settings: IntelligenceSettings,
    provider=None,
):
    ReportRequest(report_text=report_text)
    start = monotonic()
    model = settings.openai_extraction_model
    response_model = ExtractionResponse[candidate_model]

    def failure(status, warning):
        return response_model(
            extraction_status=status,
            candidate=None,
            evidence=[],
            questions=[],
            warnings=[warning],
            model=model,
            elapsed_ms=_elapsed(start),
        )

    if not settings.openai_api_key.get_secret_value() or not model or provider is None:
        return failure("unavailable", "AI extraction is unavailable. Continue with manual entry.")
    try:
        async with asyncio.timeout(settings.openai_intelligence_timeout_seconds):
            result = await provider.extract(
                report_text, catalog, model, ExtractionProposal[candidate_model]
            )
        if any(
            part.type == "refusal"
            for item in result.output
            for part in getattr(item, "content", [])
        ):
            return failure("refused", "AI extraction was refused. Continue with manual entry.")
        if result.status != "completed" or result.output_parsed is None:
            return failure("failed", "AI returned incomplete output. Continue with manual entry.")
        proposal = ExtractionProposal[candidate_model].model_validate(result.output_parsed)
        questions = validate_proposal(proposal.candidate, proposal.evidence, report_text, catalog)
        return response_model(
            extraction_status="completed",
            candidate=proposal.candidate,
            evidence=proposal.evidence,
            questions=list(dict.fromkeys([*proposal.questions, *questions])),
            warnings=list(
                dict.fromkeys(
                    [*proposal.warnings, "Review all proposed assumptions before confirmation."]
                )
            ),
            model=result.model,
            elapsed_ms=_elapsed(start),
        )
    except Exception:
        return failure("failed", "AI proposal could not be validated. Continue with manual entry.")
