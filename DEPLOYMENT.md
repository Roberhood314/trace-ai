# TRACE-AI Deployment Guide

## 1. Pi App Studio / Pi Browser frontend

Use the `web/` project as the frontend source. Set:

```env
VITE_API_BASE_URL=https://api.your-domain.example
VITE_PI_SANDBOX=false
```

The app loads the Pi SDK from `https://sdk.minepi.com/pi-sdk.js`. Production authentication is verified again by the backend through Pi's `/v2/me` endpoint.

Before production:
1. Replace the draft operator/contact details in `web/public/privacy.html`.
2. Put the actual Pi validation key at `web/public/validation-key.txt` (not the example file).
3. Build with `npm install && npm run build`.
4. Serve with HTTPS.
5. Register/verify the production domain in the Pi Developer Portal.

## 2. Backend

Recommended environment:

```env
APP_ENV=production
APP_SECRET=<long random secret>
DEV_AUTH_BYPASS=false
DATABASE_URL=postgresql+psycopg://...
CORS_ORIGINS=https://your-production-app.example
UPLOAD_DIR=/secure/persistent/path
MAX_UPLOAD_BYTES=10485760
BOOTSTRAP_ADMIN_PI_USERNAMES=<your Pi username>
```

The first matching bootstrap Pi account becomes admin. Remove the bootstrap value after the account exists.

## 3. Database

A fresh deployment can use SQLAlchemy `create_all`. Existing deployments should introduce a formal migration process before schema upgrades. Do not point this release at an older incompatible production schema without a backup/migration plan.

## 4. Evidence storage

The release stores files on a persistent backend volume and serves them only after authentication. For higher-security deployments, replace local filesystem storage with private object storage + server-authorized delivery, malware scanning, retention rules, and backups.

## 5. Reverse proxy

Terminate TLS at a reverse proxy or hosting platform. Restrict request-body size to a value consistent with `MAX_UPLOAD_BYTES`, add rate limiting, and do not expose PostgreSQL publicly.

## 6. Release checks

Run:
```bash
python -m compileall -q app
PYTHONPATH=. python -m pytest -q
cd web && npm install && npm run build
```
