# CDMS prototype

## Quick start

```bash
make env       # create .env from .env.example if it does not exist
make up        # postgres, inventory mock, cdms (runs alembic upgrade head on start)
make demo      # walk the running stack through the interesting cases
make chaos     # break the upstream, check the history survives
make verify    # prove in the database that nothing was stored twice
```

> If you don't have a virtual environment yet, run `make venv` first.

The mock on <http://localhost:8000> (docs at `/docs`).
The service on <http://localhost:8001> (docs at `/docs`). <br/>

## API

- Inbound fields follow VietFul: `eventId`, `eventType`, `occurredAt`, `warehouseCode`, `physicalQty`, etc.
- `POST /api/v1/webhooks/inventory` is the main write path; `eventId` is the idempotency key.
- Success: `200` with `status`: `applied`, `unchanged`, `stale`, or `duplicate`.
- Errors: `400` (`VALIDATION_ERROR` / `INVALID_PAYLOAD`), `401` (invalid webhook secret), `503` (database unavailable).
- Reads: `GET /api/v1/changes`, `/products/current`, `/inventories/current`, `/stats`.
- Ops: `POST /api/v1/admin/poll/run`, `GET /api/v1/poll-runs`; `/ready` checks database readiness.
- `/health` is liveness only; `/ready` is the dependency-aware probe.

## The mock

- `services/inventory_mock` emulates VietFul with deterministic data from `MOCK_SEED`.
- `GET /api/v1/Products` returns a bare array; short pages signal end-of-data.
- `POST /_admin/faults` injects `error`, `timeout`, `malformed`, or `rate_limit`.
- `POST /_admin/emit-webhook` can replay events for exactly-once testing.

## Load testing

- `make load`: 50 users / 10m — sustained load
- `make spike`: 200 users / 3m — spike load
- Both rebuild the image and require `make up` first.
- Results: `applied`, `duplicate`, `stale`, `unchanged`, `rejected`.
- Config: `.env` → `LOCUST_HOST`, `LOAD_STALE_RATE`, `LOAD_READ_WEIGHT`, `LOAD_SKUS_PER_USER`, `LOAD_POLL_WEIGHT`.
- UI: `docker compose --profile load up --build loadtest` → `http://localhost:8089`
- Recommended: `make up` → `make demo` → `make load` → `make verify` → `make spike`

## Layout

- `services/cdms` is the service: `api`, `services`, `workers`, `repositories`, `migrations`, `schemas`, `models`, `db`.
- `services/inventory_mock` is the stand-in.
- `services/loadtest` the Locust suite,
- `scripts` the demo, chaos and verification scripts.
