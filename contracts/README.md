# Shared API contracts
FastAPI/Pydantic are the source of truth. `openapi.json` is generated, never hand-edited.
From the repository root, after installing Python dependencies:

```bash
python apps/api/scripts/export_openapi.py
cd apps/web
npm run generate:api
```

`/health`, the three Feature 1 facility endpoints, the Feature 2 capacity endpoint
and the two Feature 3 network endpoints are implemented. The Feature 4 forecast
endpoint (`docs/feature-4-forecast-contract.md`) and the Feature 5 `/scenarios`
incident, baseline and simulation endpoints, Feature 5 intelligence endpoints and the
Feature 6 allocation run endpoints and the Feature 7 investment catalog/run endpoints
and the Feature 8 decision endpoints (reviews pending the outcome engine) are
implemented. Other domain module
routers remain placeholders. Examples for each feature are in `examples/feature-N/`.
Before implementing a domain endpoint, agree on its request/response schemas,
units and error cases, commit examples, then regenerate the contract and types.
The sample scenario in examples is a design fixture, not an implemented endpoint.

## Active Feature 1 contract
Read `docs/feature-1-contract.md` (from the repository root). The planned domain
design contract is `feature-1.openapi.json`; examples are in `examples/feature-1/`.
Generate it with `python apps/api/scripts/export_feature_1_contract.py`, then
`npm run generate:feature-1 --prefix apps/web`. The implemented endpoints are also
in the live `openapi.json`; frontend aliases consume its generated `schema.d.ts`.
Keep that export accurate to the running API.
