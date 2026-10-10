# Shared API contracts
FastAPI/Pydantic are the source of truth. `openapi.json` is generated, never hand-edited.
From the repository root, after installing Python dependencies:

```bash
python apps/api/scripts/export_openapi.py
cd apps/web
npm run generate:api
```

Only `/health` is currently implemented. Domain module routers are placeholders.
Before implementing a domain endpoint, agree on its request/response schemas,
units and error cases, commit examples, then regenerate the contract and types.
The sample scenario in examples is a design fixture, not an implemented endpoint.

## Active Feature 1 contract
Read `docs/feature-1-contract.md` (from the repository root). The planned domain
contract is `feature-1.openapi.json`; examples are in `examples/feature-1/`.
Generate it with `python apps/api/scripts/export_feature_1_contract.py`, then
`npm run generate:feature-1 --prefix apps/web`. These endpoints are not live yet.
Keep the regular openapi.json export accurate to the running API.
