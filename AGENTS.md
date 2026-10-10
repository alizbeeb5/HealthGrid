# HealthGrid contributor guidance

Read `docs/architecture.md` and `docs/team-ownership.md` before changing features.

- Keep the agreed monorepo and modular FastAPI backend; preserve module ownership.
- Keep authoritative calculations in Python engines, separate from HTTP, database and AI calls.
- Agree on Pydantic contracts and example payloads before integrating a new endpoint.
- Regenerate `contracts/openapi.json` and frontend API types after changing contracts.
- Coordinate shared database models and migrations with the backend/data owner.
- Preserve reported observations; scenarios use separate assumptions and snapshots.
- Label synthetic data and expose units, provenance, uncertainty and infeasibility.
- Keep secrets server-side and out of Git. Never commit real patient data.
- Do not imply placeholder screens or modules are implemented functionality.
- Use Python 3.12 and Node 22. Run checks relevant to your change; report checks that
  could not run. Local startup and check commands are in README.md.
