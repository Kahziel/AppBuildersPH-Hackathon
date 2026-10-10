# TorqueDoc 1.4.1 — verification

Date: 10 October 2026. Environment: Linux, Python 3.12, PyMuPDF 1.26.6, SQLite FTS5 and Chromium 141 headless. The test document is fictional.

## Automated results from this run

| Check | Result |
| --- | --- |
| Python API, persistence, importer and desktop-launcher suite | 62 passed |
| Desktop browser acceptance | 15 passed |
| Browser/mobile acceptance | 11 passed |
| Mobile AI lifecycle and evidence regressions | 11 passed |
| JavaScript syntax checks | Passed |
| Android application build | Passed, version 1.4.1 / 141 |
| Separate Android instrumentation APK compilation | Passed; not executed |
| Application APK signature verification | Passed, v3 |
| Application APK ZIP alignment | Passed |

Desktop and browser acceptance recorded no application JavaScript exceptions or external browser requests. Tests cover machine boundaries, PDF/source viewing, missing-model fallback, unsupported questions, maintenance-note persistence, import/revision flows and mobile layout. The added browser checks verify Request-object handling and cancellation reaching the inference engine.

The mobile lifecycle tests cover cancellation while loading and generating, recovery after cancellation, blocked mid-question model/GPU changes, failed-worker disposal, cancelled downloads, invalid replies, explicit missing specifications, unrelated components and hyphenated machine identifiers.

## Actual local-model test

Qwen2.5-0.5B-Instruct Q4_K_M was run in the application's bundled wllama runtime, with CPU inference. The official 491,400,032-byte model was downloaded beforehand and supplied through a local test mirror for browser setup. After setup, external requests were blocked. This is real inference, not a mocked model or cloud API.

Cold model start: **5.69 s**.

| Question | Result | Elapsed | Cited PDF pages |
| --- | --- | --- | --- |
| What is the cover bolt torque? | supported | 43.78 s | 2 |
| What is the coolant capacity? | not_found | 0.01 s | None |
| What is the fuel pump torque? | not_found | 0.01 s | None |
| What is the CAT 320D cover bolt torque? | not_found | 0.01 s | None |

Only the supported example invokes generation after the conservative specification checks. The three refusals happen before generation because the retrieved text lacks direct evidence. These results establish the tested cases, not general answer accuracy.

With the browser explicitly offline and the preview server stopped, the application was reloaded and the cached model loaded again in **3.45 s**. Separate browser acceptance also verified searching and drawing original PDF pages with the preview server stopped. Raw model output, timings and questions are retained in `output/real-ai-report.json`.

An earlier trial caught two false positives in unfiltered selection (missing coolant capacity and a fuel-pump torque question). The component/unit/absence checks were added, and those exact failures were rechecked successfully. They can also reject valid but ambiguous/split-table passages; inspect the original PDF in that situation.

## Practical limits

- No physical Android handset or Windows execution took place in this run.
- This newly built APK was not installed or exercised in an emulator. Do not carry forward the previous version's emulator claims as fresh evidence.
- The actual desktop Ollama model, optional 1.5B browser model, GPU acceleration, phone file pickers and mobile memory pressure were not verified.
- No OEM procedure accuracy, maintenance safety, complete revision handling or broad semantic-model accuracy is claimed.
- OCR, phone PDF ingestion, voice, automatic wiring/diagnostics and synchronization remain outside the MVP.

Use `README.md` for repeatable test commands and `ANDROID-README.md` for device checks.
