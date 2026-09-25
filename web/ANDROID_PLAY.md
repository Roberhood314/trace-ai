# TRACE AI X — Android / Google Play

This branch is isolated from production. Do not merge until Android release testing passes.

## Application identity
- App name: TRACE AI X
- Application ID: ai.trace.traceai
- Web bundle: web/dist
- Production API/domain: https://tracevnid.fyi
- Android target: API 36

## Bootstrap Android locally / CI
From `web/`:

```bash
npm ci
npm run build
npx cap add android
npx cap sync android
npx cap open android
```

Before generating a release bundle, set Android compileSdk/targetSdk to 36, versionCode/versionName, configure the release signing key outside Git, and verify the manifest only requests permissions actually used by the app.

Expected runtime permissions for current mobile scan features:
- CAMERA — only after explicit user action.
- ACCESS_FINE_LOCATION / ACCESS_COARSE_LOCATION — only for user-initiated GPS scan/location features.
- INTERNET — network access.

Do not request background location unless a future feature genuinely requires it and Google Play disclosure/review is completed.

## Release gate
1. npm build passes.
2. Android Gradle build passes with target API 36.
3. Camera and GPS permission denial/retry paths tested.
4. Pi authentication tested on the Android runtime.
5. Fusion/UAS APIs tested end-to-end.
6. Privacy Policy and Google Play Data safety answers match actual collection/retention.
7. Signed AAB uploaded to Internal testing first.
