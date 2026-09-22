# TRACE-AI Security Notes

## Access model
- `viewer`: read cases, timeline, zones, evidence, AI summary.
- `analyst`: viewer + create cases/profiles/events/zones/evidence.
- `commander`: analyst + case audit.
- `admin`: commander + user/role management.

Pi identity is verified server-side and TRACE-AI issues a short-lived signed application session. Never trust a username/role sent by the client.

## Evidence
Evidence is not mounted as a public static directory. The content endpoint requires an authenticated viewer or higher role and records an audit event.

## Development bypass
`DEV_AUTH_BYPASS=true` is for local development/tests only. It must be false in production.

## Data minimization
Only ingest data needed for an authorized case. Do not implement ambient scanning of nearby users/devices, hidden geolocation collection, unauthorized telecom data access, or unrestricted public-camera ingestion.

## Secrets
Never commit:
- Pi API/server keys
- APP_SECRET
- database passwords
- private keys
- real case records/evidence

## Production hardening still required
- Store secrets in Railway, rotate `APP_SECRET` through a planned maintenance window, and keep it at least 32 characters.
- Use encrypted backups/storage, private evidence object storage, malware scanning and a retention/deletion policy before sensitive production use.
- TRACE-AI enforces app-level request limits. Add a distributed WAF/rate limiter at the edge before public scale-out.
- Alembic controls schema changes; never deploy a migration without a tested backup restore.
- Audit events form a hash chain for tamper detection. Export audit data to a restricted log store for independent retention.
- Maintain an incident runbook and alert on readiness failures, queue failures, unusual 401/429/5xx rates and worker lease recovery.
