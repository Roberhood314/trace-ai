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
- managed secrets
- encrypted backups/storage
- malware scanning for uploads
- rate limits/WAF
- formal DB migrations
- retention/deletion policy
- incident response/log monitoring
