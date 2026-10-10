"""Safe error categories; never expose exception messages, bodies or report text."""

from openai import APIConnectionError, APIStatusError, APITimeoutError
from pydantic import ValidationError


def failure_warning(error: Exception, stage: str) -> str:
    if isinstance(error, (TimeoutError, APITimeoutError)):
        detail = "OpenAI did not finish before the request timeout. Try again."
    elif isinstance(error, APIConnectionError):
        detail = "The server could not connect to OpenAI. Check its network connection."
    elif isinstance(error, APIStatusError):
        status = error.status_code
        if status == 401:
            detail = "OpenAI rejected the server API key. Check the configured key."
        elif status in (403, 404):
            detail = (
                "OpenAI denied access to the configured model or endpoint. Check project access."
            )
        elif status == 429:
            detail = (
                "The OpenAI API quota is exhausted. Check project billing and spending limits."
                if error.code == "insufficient_quota"
                else "OpenAI rate-limited this request. Wait before trying again."
            )
        elif status in (400, 422):
            detail = (
                "OpenAI rejected the request configuration. "
                "Check the model, structured-output schema and request parameters."
            )
        elif status >= 500:
            detail = "OpenAI returned a server error. Try again later."
        else:
            detail = "OpenAI rejected this request. Check the server configuration."
    elif stage == "evidence":
        detail = "The AI proposal references unsupported hospital details or report evidence."
    elif isinstance(error, ValidationError) or stage == "schema":
        detail = "The AI response did not match the required incident or guidance format."
    else:
        detail = "The AI provider failed unexpectedly. Check the server integration."
    return f"{detail} Your incident fields are unchanged."
