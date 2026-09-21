# TRACE-AI — Pi App Studio Release Candidate

## Upload target
Use the contents of `web/` as the Pi-facing frontend source. The full repository also contains the FastAPI backend.

## Release 1.1.0-rc1
- Pi SDK login
- Server-side Pi identity verification
- Signed TRACE-AI session
- Role-based access control
- Case creation
- Missing-person profile
- Timeline with authorized source + coordinates
- Leaflet/OpenStreetMap command map
- Search zones
- Protected evidence upload/view
- AI decision-support summary
- Audit log
- Admin role management
- Privacy Policy template
- Pi domain-validation placeholder
- Radar truy nã trực quan
- Tra cứu và đồng bộ dữ liệu công khai từ Cổng thông tin truy nã Bộ Công an

## Environment
Local:
```env
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_PI_SANDBOX=true
```

Production:
```env
VITE_API_BASE_URL=https://your-api.example
VITE_PI_SANDBOX=false
```

## Before publishing
1. Replace Privacy Policy operator/contact details.
2. Add the real Pi `validation-key.txt`.
3. Set production API URL.
4. Set `VITE_PI_SANDBOX=false`.
5. Use HTTPS.
6. Configure backend `APP_SECRET`, CORS, database and first admin.
7. Do not upload real case data until storage/retention/legal controls are configured.

## Intentionally excluded
TRACE-AI does not implement ambient IP/GPS scanning of nearby users, unauthorized telecom/customer-data access, unrestricted public-camera ingestion, or phone-based thermal/fingerprint forensics.
