# TorqueDoc 1.4.1

An offline manual-search and source-selection MVP for heavy-equipment technicians. This release continues the supplied TorqueDoc project and includes a rebuilt Android APK, the Windows desktop source and launcher, and a ready-built browser application.

Start with `START-HERE.txt`.

## Run it

| Version | Start | Local AI |
| --- | --- | --- |
| Android 9+ | Install `output/TorqueDoc-Android.apk` | Settings → download the 491 MB Fast model once; subsequent inference stays on the phone |
| Windows 10/11 | Double-click `Start-TorqueDoc.bat` | Optional Ollama with `qwen3:4b`; run `setup-model-windows.bat` after installing Ollama |
| Browser on a laptop | `python website/preview.py`, then `http://127.0.0.1:8080` | Same on-device model as Android, downloaded through Settings |

The Android app bundles its interface, four reference documents, search index, PDF renderer and AI runtime. Keyword search and page viewing work before any model download. The model weights are separate and are not included in this ZIP.

The Windows launcher installs its dependencies on first use, creates working desktop/Start-menu shortcuts, then opens the app. Python 3.12 or 3.13 is supported. If automatic setup fails, install Python, run `setup-windows.bat`, then `start-windows.bat`. The desktop server uses `http://127.0.0.1:4173`.

The browser version needs localhost or HTTPS. Do not open its HTML using a `file://` address. After the first successful load, its service worker saves the application and manuals for offline reopening. Keep the same browser profile/origin; clearing site data removes local models and notes. For a phone, installing the APK avoids reliance on a first website visit.

## Working MVP features

- Machine-specific offline full-text search, including part numbers, fault codes and stemming.
- Original PDF pages with page-number, page-label and revision citations.
- Optional local AI selecting retrieved passages. Displayed specifications come from the original manual text.
- Explicit keyword-search fallback when a model is absent, fails to load or returns an invalid answer.
- Maintenance notes, local persistence, and JSON export/import.
- Desktop PDF import, manual revisions, replacement relationships, metadata editing and deletion.
- Desktop capture of web references for later offline reading, with separate web-source labels.
- A responsive dark interface for laptop and phone screens.

The bundled library contains a fictional TD-01 training manual and three third-party equipment-specification snapshots. It does not constitute a manufacturer-approved service library. The training values must never be used for maintenance.

## Changes completed in this release

- Cancellation reaches the mobile inference engine and releases it for the next question. Aborting while a model loads prevents generation from starting afterward.
- Model/GPU controls cannot change during a question. Failed model workers are discarded before retry.
- Model downloads have cancellation, available-storage checks, completion validation and clearer errors. Persistent browser storage is requested when supported.
- Slow forced-JSON generation is replaced by a short reply with strict post-validation; invalid or invented passage IDs produce keyword fallback.
- Conservative checks prevent selected numeric specifications from being promoted when the component is absent, the excerpt lacks a quantity with units, or it explicitly says the requested specification is unavailable.
- The browser API adapter preserves Request objects and propagates cancellation without retaining abort listeners.
- Android 1.4.1 is rebuilt and signed with the original project's development key. Its build and instrumentation-build scripts now support Windows, Linux and macOS toolchains.
- Windows shortcuts no longer target a missing EXE. The icon and version resource required by the portable-build recipe are included.

The numeric checks intentionally prefer refusing uncertain matches. They are heuristics, not proof of applicability, completeness or safety. A synonym, unusual unit, split table or value outside the model's excerpt can require manual inspection. Always check the original page, adjoining conditions, exact variant and current revision.

## Two-minute demo

1. Open the **Training rig · TD-01 (fictional)** workspace.
2. Search **What is the cover bolt torque?** and open original page 2, label TRAIN-8.
3. If the Fast model is installed, ask the same question with AI. The answer should cite page 2.
4. Ask **What is the coolant capacity?** or **What is the fuel pump torque?** The AI path refuses an unsupported specification; keyword matches remain available for inspection.
5. Add a maintenance note, reload, and confirm it remains.
6. Turn off internet access and repeat search/page viewing. The downloaded browser model was also checked after an offline reload.

## Update the manuals

For the desktop application, put permitted PDFs into the appropriate machine folder under `library/`, using `library/catalog.json` for title, variant, revision and type. See `library/README.txt`. Restart the desktop app to index changes. The app's **Add an update** flow handles revisions and bulletins without modifying the built-in originals.

Rebuild the browser application after library changes:

```sh
python -m pip install -r requirements.txt
python website/build.py
```

Rebuild Android after changing its bundled library or interface:

```sh
python build-android.py
```

This requires Java 17+, Android platform 36 and build-tools 36.0.0. Set `ANDROID_SDK_ROOT` and optionally `JAVA_HOME`. The SDK, emulator and private signing key are not included in the finished ZIP. To preserve installed app data across your own future builds, reuse the original project's development keystore through `TORQUEDOC_KEYSTORE`; otherwise a new key is generated. See `ANDROID-README.md`.

For a Windows portable EXE, run `build-exe.bat` on Windows after setup. It produces `dist/TorqueDoc-portable.zip`. A Windows EXE cannot be inferred from the Linux checks and is not included as a prebuilt deliverable.

## Verification

See `VALIDATION.md` for the current evidence: 62 backend tests, 15 desktop-browser checks, 11 mobile/browser checks, 11 mobile AI regression tests, an actual Qwen 0.5B browser inference test, offline model reload, and APK signature/alignment verification.

Re-run the automated checks:

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
npm run check
npm run test:mobile
python -m pip install playwright==1.56.0
python -m playwright install chromium
python tests/browser_smoke.py
python website/build.py
python website/tests/web_smoke.py
```

The optional real-model benchmark is `python website/tests/ai_bench.py cpu`; it downloads the model and can take several minutes. Test against your own permitted documents and actual target devices before relying on the app.

## Scope that remains outside this MVP

OCR, voice input, automatic schematic interpretation, automated diagnostic conclusions, shop synchronization and iOS packaging are not implemented. Wiring and troubleshooting screens remain explicitly labeled design previews. New PDFs are added on the desktop and bundled for Android/browser by rebuilding; phone-side PDF ingestion is not implemented.

This version was not executed on a physical Android handset or on Windows. Android installation, file pickers, memory pressure, GPU behavior and inference latency still need device checks. The optional 1.5B mobile model and the actual desktop Ollama model were not run in this verification.

## Data locations

`library/` holds built-in references. Desktop imports and indexes go to `data/`. Notes and browser models live in the relevant app/browser storage. Export maintenance logs before uninstalling, clearing storage or changing browser profiles. The original Drive ZIP was left unchanged.
