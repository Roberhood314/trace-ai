# TRACE AI X Google Play release gate

## Build
- [x] Isolated branch: android-play-production
- [x] Capacitor Android bootstrap
- [x] Application ID: ai.trace.traceai
- [x] CI enforces compileSdk/targetSdk 36
- [x] CI creates unsigned release AAB
- [ ] Release signing keystore configured as GitHub/Play secret
- [ ] Signed AAB verified

## Permissions and privacy
- [x] INTERNET
- [x] CAMERA
- [x] ACCESS_COARSE_LOCATION
- [x] ACCESS_FINE_LOCATION
- [x] Background location explicitly rejected by CI
- [ ] In-app permission rationale/denial UX verified on device
- [ ] Privacy Policy final URL verified
- [ ] Data Safety form completed from actual data flows
- [ ] Account/data deletion flow verified if account creation is offered

## Functional release test
- [ ] Cold start
- [ ] Pi Sign-In / Android authentication path
- [ ] Wanted search + portraits
- [ ] Map/GPS
- [ ] Camera scan
- [ ] Fusion status/tracks
- [ ] Network loss/recovery
- [ ] Logout/session expiry

## Play rollout
- [ ] Internal testing
- [ ] Pre-launch report clean
- [ ] Closed/Open testing if required
- [ ] Production rollout approval
