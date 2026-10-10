# Mobile runtime notes — 1.4.1

Android packaging is now included: `output/TorqueDoc-Android.apk`. See `ANDROID-README.md`.

The browser and Android shell share SQLite search, PDF rendering and wllama AI. The 0.5B model was exercised in Chromium with external requests blocked; final timings and refusal cases are in `VALIDATION.md`. It remains experimental on actual phones. The compatibility worker and WASM are bundled locally for older WebViews.

The build includes cancellation, protected model changes, storage checks and conservative numeric-evidence filtering. Model responses are validated, and only retrieved source text can be displayed as evidence. Incorrect semantic selection remains possible; always inspect the original page.

New PDFs are added through the desktop library and bundled by rebuilding the website/APK. Phone-side ingestion, OCR and iOS packaging remain unimplemented. Model download/import retention and device-specific performance must be checked on the target phone.
