# TRACE-AI Web — Pi App Studio

React/Vite frontend for Pi Browser and Pi App Studio.

## Local
```bash
npm install
cp .env.example .env
npm run dev
```

## Build
```bash
npm install
npm run build
```

Output: `dist/`.

## Pi
The Pi SDK is loaded in `index.html`. Pi authentication returns an access token which is verified by TRACE-AI backend before a signed app session is stored in the browser.

## Static production files
- `public/privacy.html`: privacy policy template; replace operator details.
- `public/validation-key.txt.example`: rename/create the actual `validation-key.txt` from Pi Developer Portal.

## Release validation
GitHub Actions Web Build passed for release candidate 1.0.0-rc1.
