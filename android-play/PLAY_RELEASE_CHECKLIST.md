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
- [x] Native Camera/Geolocation permission requests implemented
- [ ] In-app permission denial/retry UX verified on physical device
- [ ] Privacy Policy final URL verified
- [ ] Data Safety form completed from actual data flows
- [x] Account deletion API + in-app action implemented
- [ ] Account/data deletion flow verified against production database

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


## Reviewer access
- [x] Dedicated server-side Google Play reviewer login implemented.
- [x] Demo Admin fallback removed from production frontend.
- [ ] Configure PLAY_REVIEWER_USERNAME and PLAY_REVIEWER_PASSWORD in production.
- [ ] Enter the same reviewer credentials/instructions in Play Console App access.

## Remaining external gates
- [ ] Add Android signing secrets in GitHub Actions.
- [ ] Confirm successful signed AAB workflow artifact.
- [ ] Upload AAB to Google Play Internal testing.


## Final Google Play compliance pass — 2026-09-25
- [x] External account-deletion web resource implemented at /delete-account.html.
- [x] External deletion request API implemented; ownership verification required before deletion.
- [x] Reviewer account elevated to read-only reviewer role for restricted read screens.
- [x] Reviewer write operations blocked server-side.
- [x] CI artifact explicitly marked as signed/unsigned in signing-state.txt.
- [x] Data Safety declaration worksheet added to repository.
- [ ] Configure Android upload/signing key secrets (account-owner action).
- [ ] Configure PLAY_REVIEWER_USERNAME / PLAY_REVIEWER_PASSWORD in production environment.
- [ ] Copy final Data Safety answers into Play Console.
- [ ] Upload signed AAB to Internal testing and clear Pre-launch report.
