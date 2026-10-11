# Security review and operating limits

This is a private planning prototype, not a certified clinical or public service.
No change can make attacks impossible. This review uses local, bounded tests and
isolated databases; it does not flood the host or call paid AI providers.

## Implemented protections

- Both the Next server and FastAPI independently verify optional shared Basic
  credentials using constant-time digest comparisons. Secrets are server-side.
  `APP_ENVIRONMENT=production` fails closed without configured credentials.
- Production rejects the simulated Beirut approval exercise, requires explicit
  HTTPS browser origins and allowed hosts, and disables API schema/docs routes.
- Cross-site Fetch Metadata and unapproved browser write origins are rejected.
  The backend accepts JSON request bodies only and rejects compressed bodies.
- Mutation bodies are limited to 1 MiB, including streamed bodies without a
  truthful Content-Length. Body reads time out after 15 seconds. Excessive nesting,
  collections, query strings and paths are rejected. Framework errors do not echo
  submitted values. Next buffers at most 1 MiB in its proxy; that buffering option
  is not itself a complete streaming-request rejection mechanism.
- Backend admission uses 600 requests/minute and 120 writes/minute per direct
  peer, 30 expensive requests/minute globally, and at most two expensive requests
  concurrently per process. Calculations, AI calls, review capture and demo stage
  advancement share the expensive budget. Defaults can be reduced through settings.
- Forwarded IP headers are deliberately ignored by the limiter. Docker's proxy
  may make clients share one peer budget. Limiter storage is bounded to 2048 entries;
  quotas reset when the process starts and are not coordinated between workers.
- Optimization/incident input collections and integer amounts are bounded.
  Server-selected solver timeouts remain in place. Contracts/types were regenerated.
- The frontend uses per-response script nonces, production script execution without
  unsafe-eval, framing/object restrictions and no-sniff/privacy headers. Rendering
  is dynamic so Next's scripts receive matching nonces. Leaflet/Recharts positioning
  still requires inline styles; development permits eval and HMR WebSockets.
- Compose keeps ports on loopback, drops app-container capabilities, prevents new
  privileges, and bounds app memory, CPU, process counts and API connections.
  The frontend runs as the non-root `node` user. Development API documentation
  permits its CDN/inline bootstrap under a separate policy; production removes it.

## Access configuration

For a shared login on the existing local Docker app, put a generated password of
at least 16 characters in the ignored root `.env`:

```dotenv
SECURITY_USERNAME=healthgrid
SECURITY_PASSWORD=<generated-unique-password>
```

Recreate frontend and backend containers to apply environment changes. The browser
prompts for credentials; API clients use HTTP Basic as well. Keep secrets out of
`NEXT_PUBLIC_*`, source control, screenshots and logs. Basic auth must be behind
TLS for any remote use. It is a shared gate, not individual identities, roles,
verified approval signatures or multi-factor authentication.

The reviewed local Docker instance has this login enabled. Its generated password
is stored only in the ignored root `.env` under `SECURITY_PASSWORD`.

For production additionally set `APP_ENVIRONMENT=production`, explicit JSON arrays
for `SECURITY_ALLOWED_HOSTS` and `SECURITY_ALLOWED_ORIGINS` (HTTPS only), remove the
Beirut override and use production server/image commands rather than development
reload servers. Do not expose development services by forwarding their ports.

## What still requires deployment work

- A trusted TLS gateway must enforce HTTPS/HSTS, strip untrusted forwarding headers,
  enforce header/body/read timeouts, bound connections and provide shared quotas.
- A CDN/WAF or hosting provider must absorb volumetric DDoS; application middleware
  cannot protect network bandwidth, Next's server resources or multiple replicas
  against a distributed flood. Frontend authentication attempts need edge throttling.
- Individual accounts, authorization per hospital/action, MFA, session lifecycle and
  trusted audit identities are not implemented by the shared login. Never use real
  patient data or operational approvals with simulated actors.
- Development images/bind mounts and the local Fedora label exception are not a
  hardened production container setup. Use non-root production images, immutable
  filesystems, managed secrets, isolated networking, backups and monitoring.
- Anonymous access remains enabled in development when SECURITY_PASSWORD is blank.
  This is intentional for loopback testing, not a public deployment setting.
- CSP and input validation reduce injection risk; they do not prove that every XSS,
  SQL injection, logic error, prompt injection or future dependency issue is absent.
  AI inputs remain untrusted proposals with human confirmation and no tools/dispatch.

## Verification

Run `pytest apps/api/tests/test_security.py` and
`npm run test:security --prefix apps/web` for adversarial regression checks.
The checks cover auth denial, unsafe production configuration, malicious hosts and
origins, streamed/declared body size, nesting, nonfinite values, throttling, slow
bodies, expensive concurrency, SQL-like identifiers, HTML escaping, redirect
targets and script nonce policies. These use fixed low budgets, not stress traffic.

Dependency audits: npm runtime audit and pip-audit against `requirements.lock`.
Their absence of findings means no known advisories returned at audit time, not
proof of vulnerability-free dependencies. Re-run audits regularly.

Review results: 746 backend tests and 54 subtests passed; all four frontend security
tests, type checking, linting and the webpack production build passed. Runtime npm
and locked Python dependency audits returned no known advisories. The full frontend
suite passed 64 of 69 tests. The same five failures reproduce against unchanged HEAD
(allocation/AI/forecast copy expectations, resource-name casing and catalog loading);
they are existing test failures outside these security changes.

Authenticated local smoke checks passed for the frontend, direct API and frontend
API forwarding. Anonymous requests returned 401, cross-site writes returned 403,
and all 20 scripts in the hospital page had matching CSP nonces. Existing Beirut
exercise data remained available.
