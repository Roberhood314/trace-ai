# TRACE AI X — Play production release gate

The Android workflow can create a CI AAB even before signing secrets exist. That CI artifact is for build verification only.

A Google Play upload is allowed only when all four repository secrets are configured:
- ANDROID_KEYSTORE_BASE64
- ANDROID_KEYSTORE_PASSWORD
- ANDROID_KEY_ALIAS
- ANDROID_KEY_PASSWORD

The workflow writes `signing-state.txt` into the artifact:
- `SIGNED_RELEASE=true` → signed release candidate.
- `SIGNED_RELEASE=false` → CI smoke artifact; **do not upload to Play Console**.

Recommended release flow:
1. Configure an upload key/keystore and the four GitHub Actions secrets.
2. Run the Android Play Bundle workflow.
3. Confirm the signing verification step succeeds.
4. Confirm `signing-state.txt` says `SIGNED_RELEASE=true`.
5. Upload the resulting AAB to Google Play Internal testing.
6. Complete App access, Data Safety, Account deletion URL and store listing.
7. Clear the Pre-launch report before production rollout.
