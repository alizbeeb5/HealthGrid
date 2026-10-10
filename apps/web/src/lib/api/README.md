# API client
`npm run generate:api` generates `schema.d.ts` from the committed OpenAPI contract.
Use its `components` and `paths` types for implemented domain endpoints.
`apiGet` is a browser helper, not runtime validation. Do not call it from Server
Components with a relative URL; those need the server's absolute API_BASE_URL.
Never place OpenAI credentials here. Mock future endpoints using agreed examples.

Feature 1 uses the generated aliases in `feature-1.ts` and the browser client in
`facilities.ts`. It has explicit synthetic demo and API modes; see
`../../features/facilities/README.md` for setup and persistence semantics.

Feature 2's `capacity.ts` uses the implemented GET capacity route without falling
back to samples. `feature-2.ts` aliases the backend-owned types in generated
`schema.d.ts`. Resource saves refetch both snapshot and capacity. The panel never
calculates capacity; the optional browser demo labels its fixed samples as frozen.
