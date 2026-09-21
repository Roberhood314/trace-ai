# TRACE-AI Railway deployment

Target: HTTPS backend for Pi App Studio / Pi Browser.

Required variables:
- APP_ENV=production
- APP_SECRET=<strong random secret>
- DEV_AUTH_BYPASS=false
- DATABASE_URL=<Railway PostgreSQL DATABASE_URL>
- CORS_ORIGINS=<exact Pi App Studio / production origin>
- CORS_ORIGIN_REGEX=<optional controlled regex for Pi development origins>
- WANTED_AUTO_SYNC_MINUTES=60
- WANTED_AUTO_SYNC_PAGES=3
- WANTED_DETAIL_LIMIT=100
- UPLOAD_DIR=/data/uploads
- MAX_UPLOAD_BYTES=10485760

Optional authorized gateways:
- WEATHER_GATEWAY_URL=
- RESPONSE_UNIT_GATEWAY_URL=

After deployment:
1. GET /health
2. Sign in as Commander/Admin.
3. POST /wanted/sync?pages=3
4. GET /public/wanted
5. GET /public/wanted/{id}/image
6. Set NEXT_PUBLIC_TRACE_API_URL to the Railway HTTPS service URL in Pi App Studio.
