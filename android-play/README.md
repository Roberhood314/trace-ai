# Android Play release workspace

The Android application is generated from the existing React/Vite frontend in `web/` using Capacitor.

The generated `web/android/` Gradle project should be created with `npx cap add android` after dependencies are installed, then committed only after compile/target SDK, manifest permissions, signing placeholders, icons, splash assets, and release build have been validated.

Production Railway deployment is not changed by this branch.
