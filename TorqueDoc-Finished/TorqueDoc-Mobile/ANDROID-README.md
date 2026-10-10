# Install TorqueDoc 1.4.1 on Android

The application is `output/TorqueDoc-Android.apk` (10.4 MB).
It requires Android 9 or later and an updated Android System WebView.

1. Extract the project ZIP and copy the APK to your phone.
2. Open the APK in Files and follow Android's installation prompts.
3. Launch TorqueDoc. Search and original PDF pages are bundled and need no desktop server.
4. Select **Training rig · TD-01 (fictional)**. Search **What is the cover bolt torque?** and open PDF page 2.
5. To enable local AI, open Settings and download the Fast model once (491 MB). Keep the app open until complete, then disconnect from the internet and ask the question again.

The larger optional model is about 1.1 GB. Model files are not inside the APK. Search stays available without a model. The training manual is fictional; the other references are third-party snapshots. These are not approved service procedures.

## Upgrading and data

This APK uses package `com.torquedoc.app`, version code 141, and the original project's development signing key. Android should recognize it as an update to an app installed with that same key. Export notes before upgrading. If Android reports a signature conflict, keep the installed app and its data until you have exported notes; do not uninstall as an automatic workaround.

## What this release verified

APK construction, compilation, signature scheme v3 and ZIP alignment passed. The browser engine passed offline search, PDF viewing, persistent notes, real Qwen 0.5B inference and offline model reload. **This 1.4.1 APK was not installed on an emulator or physical phone during this run.** The earlier archive's emulator report applies to its earlier build only.

On your phone, check launch, model download, airplane-mode search, original pages, AI inference, note persistence after force-close, and JSON export/import. Actual handset performance is not predicted by the browser timing.

## Build from source

Install Python 3.12+, the Python requirements, Java 17+, Android SDK platform 36 and build-tools 36.0.0. Set `ANDROID_SDK_ROOT` and optionally `JAVA_HOME`.

```sh
python build-android.py
```

The script supports Windows, Linux and macOS. The toolchain and signing key are deliberately kept out of the delivery ZIP. Reuse the development keystore from your original archive with `TORQUEDOC_KEYSTORE` when building an update; if absent, the script creates a new development key. It is a sideloadable development build, not a Play Store release.

Optional native test package:

```sh
python build-android-tests.py
adb install -r output/TorqueDoc-Android.apk
adb install -r output/TorqueDoc-tests.apk
adb shell am instrument -w com.torquedoc.tests/com.torquedoc.tests.OfflineChecks
```

`TorqueDoc-tests.apk` is a development test package; install only `TorqueDoc-Android.apk` for normal use. The test package was built successfully here, but its instrumentation was not executed in this run.

## APK identity

SHA-256: `65a90d435220ddb30e37b3bce1d3ce82a8e2cdbd40a642f5e8d62d6ce7f65cf6`

The current exact metadata is in `output/build-info.json`.
