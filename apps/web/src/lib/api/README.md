# API client
`npm run generate:api` generates `schema.d.ts` from the committed OpenAPI contract.
Use its `components` and `paths` types when domain endpoints become available.
`apiGet` is a browser helper, not runtime validation. Do not call it from Server
Components with a relative URL; those need the server's absolute API_BASE_URL.
Never place OpenAI credentials here. Mock future endpoints using agreed examples.
