"""Bounded request admission; no domain calculations or changes to hospital data.

Limits are per process, deliberately ignore spoofable forwarding headers, and do
not replace distributed edge limits. The shared login protects a private prototype,
not individual clinical roles or verified decision actors.
"""

import asyncio
import base64
import binascii
import hashlib
import json
import math
import secrets
from collections import OrderedDict
from time import monotonic

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from app.core.config import Settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
}


def valid_credentials(header: str, settings: Settings) -> bool:
    if len(header) > 4096:
        return False
    try:
        scheme, value = header.split(" ", 1)
        if scheme.lower() != "basic":
            return False
        username, password = base64.b64decode(value, validate=True).decode().split(":", 1)
    except (ValueError, UnicodeError, binascii.Error):
        return False
    # Fixed-length digests avoid length-dependent comparisons, including Unicode.
    digest = lambda value: hashlib.sha256(value.encode()).digest()  # noqa: E731
    return secrets.compare_digest(digest(username), digest(settings.security_username)) & (
        secrets.compare_digest(
            digest(password), digest(settings.security_password.get_secret_value())
        )
    )


def bounded_json(value) -> bool:
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > 20 or count > 10_000:
            return False
        if isinstance(item, float) and not math.isfinite(item):
            return False
        if isinstance(item, (list, dict)):
            if len(item) > 1000:
                return False
            pending.extend(
                (child, depth + 1) for child in (item.values() if isinstance(item, dict) else item)
            )
    return True


class AdmissionLimits:
    def __init__(self):
        self.buckets = OrderedDict()
        self.global_buckets = {}
        self.inflight = 0

    def allow(self, key, limit):
        now = monotonic()
        # Fixed global quotas cannot be evicted by a flood of new peer addresses.
        buckets = self.global_buckets if key == ("global", "expensive") else self.buckets
        started, count = buckets.pop(key, (now, 0))
        if now - started >= 60:
            started, count = now, 0
        buckets[key] = (started, count + 1)
        while len(self.buckets) > 2048:
            self.buckets.popitem(last=False)
        return count < limit


class SecurityMiddleware:
    def __init__(self, app, settings: Settings):
        self.app, self.settings = app, settings
        self.limits = AdmissionLimits()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            self.limits = AdmissionLimits()
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        settings = self.settings
        headers = Headers(scope=scope)
        path, method = scope["path"], scope["method"]
        peer = (scope.get("client") or ("unknown", 0))[0]

        async def secure_send(message):
            if message["type"] == "http.response.start":
                current = list(message.get("headers", []))
                names = {key.lower() for key, _ in current}
                response_headers = dict(HEADERS)
                if settings.app_environment == "development" and path in {"/docs", "/redoc"}:
                    # FastAPI's development-only docs use a CDN and inline bootstrap.
                    # Production removes these routes entirely.
                    response_headers["Content-Security-Policy"] = (
                        "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net "
                        "'unsafe-inline'; style-src 'self' https://cdn.jsdelivr.net "
                        "'unsafe-inline'; img-src 'self' data: https://fastapi.tiangolo.com; "
                        "font-src 'self' https://fonts.gstatic.com; "
                        "frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
                    )
                current.extend(
                    (key.lower().encode(), value.encode())
                    for key, value in response_headers.items()
                    if key.lower().encode() not in names
                )
                message = {**message, "headers": current}
            await send(message)

        async def deny(status, code, message, extra=None):
            response = JSONResponse(
                {"error": {"code": code, "message": message, "fields": []}},
                status_code=status,
                headers=extra,
            )
            await response(scope, receive, secure_send)

        if len(scope.get("query_string", b"")) > 4096 or len(path) > 2048:
            return await deny(414, "uri_too_long", "Request URI exceeds the size limit.")

        if not self.limits.allow((peer, "all"), settings.security_requests_per_minute):
            return await deny(
                429, "rate_limited", "Too many requests. Try again later.", {"Retry-After": "60"}
            )
        if settings.security_password.get_secret_value() and path != "/health":
            if not valid_credentials(headers.get("authorization", ""), settings):
                return await deny(
                    401,
                    "authentication_required",
                    "Authentication required.",
                    {"WWW-Authenticate": 'Basic realm="HealthGrid", charset="UTF-8"'},
                )
        if headers.get("sec-fetch-site") == "cross-site":
            return await deny(403, "cross_site_request", "Cross-site requests are not allowed.")
        if method not in SAFE_METHODS:
            if headers.get("origin") and headers["origin"] not in settings.security_allowed_origins:
                return await deny(403, "origin_not_allowed", "Browser origin is not allowed.")
            if not self.limits.allow((peer, "writes"), settings.security_writes_per_minute):
                return await deny(
                    429, "rate_limited", "Too many updates. Try again later.", {"Retry-After": "60"}
                )

        expensive = method == "POST" and (
            path.startswith("/api/v1/intelligence/")
            or path.endswith("/simulate")
            or path
            in {"/api/v1/allocation/runs", "/api/v1/investments/runs", "/api/v1/demo/advance"}
            or path.endswith("/reviews")
        )
        if expensive:
            # The global bucket bounds cost across changing source addresses.
            if not self.limits.allow(
                ("global", "expensive"), settings.security_expensive_per_minute
            ):
                return await deny(
                    429,
                    "rate_limited",
                    "Calculation limit reached. Try later.",
                    {"Retry-After": "60"},
                )
            if self.limits.inflight >= settings.security_max_expensive_concurrent:
                return await deny(
                    503,
                    "server_busy",
                    "Calculations are busy. Try again later.",
                    {"Retry-After": "5"},
                )
            self.limits.inflight += 1

        try:
            if method not in SAFE_METHODS:
                if headers.get("content-encoding", "identity").lower() != "identity":
                    return await deny(
                        415, "unsupported_encoding", "Compressed requests are disabled."
                    )
                lengths = headers.getlist("content-length")
                if len(lengths) > 1 or (
                    lengths and (not lengths[0].isdigit() or len(lengths[0]) > 20)
                ):
                    return await deny(400, "invalid_request", "Invalid content length.")
                if lengths and int(lengths[0]) > settings.security_max_body_bytes:
                    return await deny(413, "request_too_large", "Request exceeds the size limit.")
                body = bytearray()

                async def read_body():
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return False
                        body.extend(message.get("body", b""))
                        if len(body) > settings.security_max_body_bytes:
                            return False
                        if not message.get("more_body", False):
                            return True

                try:
                    complete = await asyncio.wait_for(
                        read_body(), settings.security_body_timeout_seconds
                    )
                except TimeoutError:
                    return await deny(408, "request_timeout", "Request body timed out.")
                if not complete:
                    return await deny(
                        413, "request_too_large", "Request is incomplete or too large."
                    )
                if body:
                    if (
                        headers.get("content-type", "").split(";", 1)[0].lower()
                        != "application/json"
                    ):
                        return await deny(415, "unsupported_media_type", "Use application/json.")
                    try:
                        value = json.loads(body)
                        if not bounded_json(value):
                            return await deny(413, "request_too_complex", "Request is too complex.")
                    except RecursionError:
                        return await deny(413, "request_too_complex", "Request is too complex.")
                    except (ValueError, UnicodeError):
                        # Let the domain route keep its established malformed-JSON
                        # validation contract. Its body is already bounded above.
                        pass
                used = False

                async def replay():
                    nonlocal used
                    if not used:
                        used = True
                        return {"type": "http.request", "body": bytes(body), "more_body": False}
                    return await receive()

                await self.app(scope, replay, secure_send)
            else:
                await self.app(scope, receive, secure_send)
        finally:
            if expensive:
                self.limits.inflight -= 1
