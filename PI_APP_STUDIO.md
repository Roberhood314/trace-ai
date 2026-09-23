# TRACE-AI — Pi App Studio Release Candidate

## Upload target
Use the contents of `web/` as the Pi-facing frontend source. The full repository also contains the FastAPI backend.

## Release 1.5.0-rc2
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
VITE_API_BASE_URL=https://tracevnid.fyi
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
# Pi Testnet payment checklist

The optional checklist payment is a 0.01 Pi Testnet transaction with no purchase or service entitlement. It is disabled by default. Set `PI_TEST_PAYMENT_ENABLED=true` and set `PI_API_KEY` as a server-side environment variable in Railway. Never set the API key in Vite variables or commit it to git. The backend rejects payments on any network other than Pi Testnet, verifies the user's Pi UID, fixed amount, purpose, direction and verified transaction before approving or completing. Log in from Pi Browser, tap "Thử thanh toán 0,01 Pi (Testnet)", and approve the test transaction in your own Pi wallet. The app cannot make this payment on the user's behalf. Turn the toggle off again after checklist verification. A real product payment needs a separate order model and fulfillment policy.


## Canonical Pi URLs
- Production/App URL: https://tracevnid.fyi
- Development URL: https://tracevnid.fyi
- Pi Sign-In redirect URI: https://tracevnid.fyi/signin/callback
- Privacy Policy: https://tracevnid.fyi/privacy.html
- Terms of Service: https://tracevnid.fyi/terms.html
- Backend/metadata URL: https://tracevnid.fyi
- PiNet subdomain base: traceai
- Current PiNet subdomain: traceai7552
