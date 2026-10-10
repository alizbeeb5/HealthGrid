import type { components } from "../../lib/api/schema";
import type { Assessment, Extraction } from "./model";

type Schemas = components["schemas"];
type Status = Assessment["status"];

function message(status: Status, extraction: boolean): string {
  switch (status) {
    case "completed": return extraction ? "Review the extracted proposal and its evidence before using it." : "OpenAI Decisions returned these report flags. Review them alongside the original report.";
    case "unavailable": return extraction ? "AI extraction is not configured on the server. Continue with manual entry." : "OpenAI assessment is not configured on the server. Continue with manual entry.";
    case "refused": return "OpenAI declined this request. Your manual fields are unchanged.";
    case "failed": return "The AI request did not complete successfully. Your manual fields are unchanged.";
  }
}

async function reportRequest<T>(action: "assess" | "extract", report: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1/intelligence/incidents/${action}`, {
      method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ report_text: report }),
    });
  } catch { throw new Error("Could not reach AI review. Your manual fields are unchanged."); }
  let body: unknown;
  try { body = await response.json(); }
  catch { throw new Error("AI review returned an unreadable response. Your manual fields are unchanged."); }
  if (!response.ok) {
    if (response.status === 422) {
      const fields = (body as Schemas["ScenarioErrorResponse"])?.error?.fields;
      throw new Error(Array.isArray(fields) && fields.length ? fields.map((field) => `${field.field}: ${field.message}`).join(" ") : "The incident report is invalid.");
    }
    throw new Error("AI review is unavailable. Your manual fields are unchanged.");
  }
  return body as T;
}

export async function assessIncidentReport(report: string): Promise<Assessment> {
  const result = await reportRequest<Schemas["AssessmentResponse"]>("assess", report);
  return {
    status: result.assessment_status,
    answers: result.answers.map((answer) => ({ question: answer.name, value: answer.value, answer_status: answer.answer_status === "completed" ? "answered" : "refused" })),
    model: result.model, elapsed_ms: result.elapsed_ms, rubric_version: result.rubric_version,
    message: message(result.assessment_status, false),
  };
}

export async function extractIncidentReport(report: string): Promise<Extraction> {
  const result = await reportRequest<Schemas["ExtractionResponse_IncidentDraftInput_"]>("extract", report);
  return {
    status: result.extraction_status, candidate: result.candidate, evidence: result.evidence,
    questions: result.questions, warnings: result.warnings, model: result.model,
    elapsed_ms: result.elapsed_ms, message: message(result.extraction_status, true),
  };
}
