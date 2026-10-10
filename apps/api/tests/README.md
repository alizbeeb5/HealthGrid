# Backend tests
Place constraint/feasibility tests, forecast backtests, ingestion validation and API
integration tests here as those features are implemented. Numerical engine tests
should run without PostgreSQL or an OpenAI key.

Feature 1 contract and pure observation-validation tests are in
`test_observation_validation.py`. Run from the repository root with `pytest`, or
with the standard-library runner in the selected environment:

```bash
PYTHONPATH=apps/api .venv/bin/python -m unittest discover -s apps/api/tests -v
.venv/bin/python apps/api/scripts/check_feature_1_examples.py
```

The backend resolves facility existence and resource applicability, then calls
`validate_observation(observation, resource, now)` from `ingestion.validation`.
An empty list means valid; otherwise map the returned FieldError entries to the
agreed 422 ErrorResponse. Map Pydantic shape errors to the same envelope. A missing
facility is 404; an unknown or inapplicable resource is a `resource_id` field error.
These lookup and HTTP behaviors still require backend integration tests.

Shared valid and invalid cases live in `contracts/examples/feature-1/`.
`validation_layer` is fixture metadata: `shape` means Pydantic, `catalog` means
the pure validator (including server-time checks), and `resource_lookup` means
backend resolution. Old reports and zero are valid; missing data is represented
only in snapshots, not by submitting a null quantity.
