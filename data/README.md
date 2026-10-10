# Demo data
All records in `synthetic/` are fictional. Coordinates are illustrative, not verified
hospital locations. These fixtures do not establish forecasting accuracy.

Templates define initial import column conventions; no importer exists yet.
Use stable string IDs, explicit resource units and ISO 8601 UTC observation times.
Keep observations separate from assumptions. Never commit patient data, real
facility reports, credentials, or private datasets. Historical demand and resource
fixtures will be added when the team's shared domain schemas are agreed.

Feature 1 canonical IDs, field names and mock snapshots are defined in
`docs/feature-1-contract.md` and `contracts/examples/feature-1/` (repository-relative).
Use those when preparing seed/import data; do not invent alternate field names.
