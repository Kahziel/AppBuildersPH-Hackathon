"""Build the offline Android app on Windows, Linux or macOS.
Requires Python 3.12+, PyMuPDF, Java 17+, Android platform 36 and build-tools 36.0.0.
Set ANDROID_SDK_ROOT (or ANDROID_HOME) and optionally JAVA_HOME.
Usage: python build-android.py [--skip-web]
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
SDK = Path(os.environ.get('ANDROID_SDK_ROOT') or os.environ.get('ANDROID_HOME') or ROOT / '.android-tools' / 'sdk')
TOOLS = SDK / 'build-tools' / '36.0.0'
ANDROID = SDK / 'platforms' / 'android-36' / 'android.jar'
BUILD = ROOT / 'build' / ('android-' + str(time.time_ns()))
OUT = ROOT / 'output'
SUFFIX = '.exe' if os.name == 'nt' else ''


def java_executable(name='java'):
    home = os.environ.get('JAVA_HOME')
    candidate = Path(home) / 'bin' / (name + SUFFIX) if home else None
    return str(candidate) if candidate and candidate.is_file() else shutil.which(name)


def run(*args):
    print('Running:', Path(str(args[0])).name, flush=True)
    subprocess.run([str(a) for a in args], check=True, cwd=ROOT)


def main():
    java = java_executable()
    aapt, align = TOOLS / ('aapt2' + SUFFIX), TOOLS / ('zipalign' + SUFFIX)
    for path in [aapt, align, ANDROID, TOOLS / 'lib/d8.jar', TOOLS / 'lib/apksigner.jar']:
        if not path.is_file():
            raise SystemExit(f'Missing Android build dependency: {path}. Set ANDROID_SDK_ROOT to your Android SDK.')
    if not java:
        raise SystemExit('Java 17+ is required. Install a JDK and set JAVA_HOME.')
    if '--skip-web' not in sys.argv:
        subprocess.run([sys.executable, str(ROOT / 'website/build.py')], cwd=ROOT, check=True)
    assets = BUILD / 'assets/public'
    shutil.copytree(ROOT / 'website/dist', assets)
    shutil.copy2(ROOT / 'android/native-bootstrap.js', assets / 'native-bootstrap.js')
    html = (assets / 'index.html').read_text(encoding='utf-8')
    (assets / 'index.html').write_text(html.replace('<head>', '<head>\n    <script src="./native-bootstrap.js"></script>'), encoding='utf-8')
    classes, dex = BUILD / 'classes', BUILD / 'dex'
    classes.mkdir(); dex.mkdir(); OUT.mkdir(exist_ok=True)
    run(aapt, 'compile', '--dir', ROOT / 'android/res', '-o', BUILD / 'resources.zip')
    run(aapt, 'link', '-o', BUILD / 'unsigned.apk', '-I', ANDROID,
        '--manifest', ROOT / 'android/AndroidManifest.xml', '-R', BUILD / 'resources.zip', '-A', BUILD / 'assets')
    sources = sorted((ROOT / 'android/src').rglob('*.java'))
    compiler = [java_executable('javac')] if java_executable('javac') else [java, 'com.sun.tools.javac.Main']
    run(*compiler, '--release', '8', '-encoding', 'UTF-8', '-classpath', ANDROID, '-d', classes, *sources)
    with zipfile.ZipFile(BUILD / 'classes.jar', 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(classes.rglob('*.class')):
            archive.write(file, file.relative_to(classes).as_posix())
    run(java, '-cp', TOOLS / 'lib/d8.jar', 'com.android.tools.r8.D8', '--lib', ANDROID,
        '--min-api', '28', '--output', dex, BUILD / 'classes.jar')
    with zipfile.ZipFile(BUILD / 'unsigned.apk') as source, zipfile.ZipFile(BUILD / 'with-dex.apk', 'w', zipfile.ZIP_DEFLATED) as archive:
        for item in source.infolist():
            archive.writestr(item, source.read(item.filename), compress_type=zipfile.ZIP_STORED if item.filename == 'resources.arsc' else item.compress_type)
        archive.write(dex / 'classes.dex', 'classes.dex')
    run(align, '-f', '4', BUILD / 'with-dex.apk', BUILD / 'aligned.apk')
    key = Path(os.environ.get('TORQUEDOC_KEYSTORE', ROOT / '.signing/torquedoc-development.jks'))
    key.parent.mkdir(parents=True, exist_ok=True)
    if not key.exists():
        keytool = [java_executable('keytool')] if java_executable('keytool') else [java, 'sun.security.tools.keytool.Main']
        run(*keytool, '-genkeypair', '-keystore', key, '-storepass', 'android', '-keypass', 'android',
            '-alias', 'torquedoc-development', '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000',
            '-dname', 'CN=TorqueDoc Development,O=TorqueDoc,C=PH', '-noprompt')
    apk = OUT / 'TorqueDoc-Android.apk'
    signer = [java, '-jar', TOOLS / 'lib/apksigner.jar']
    run(*signer, 'sign', '--ks', key, '--ks-key-alias', 'torquedoc-development',
        '--ks-pass', 'pass:android', '--key-pass', 'pass:android', '--out', apk, BUILD / 'aligned.apk')
    run(*signer, 'verify', '--verbose', apk)
    run(align, '-c', '4', apk)
    manifest = ET.parse(ROOT / 'android/AndroidManifest.xml').getroot()
    ns = '{http://schemas.android.com/apk/res/android}'
    info = {'apk': apk.name, 'version': manifest.get(ns + 'versionName'), 'version_code': int(manifest.get(ns + 'versionCode')),
        'package': manifest.get('package'), 'min_android': 9,
        'bytes': apk.stat().st_size, 'sha256': hashlib.sha256(apk.read_bytes()).hexdigest(),
        'signing': 'original project development key; sideload/testing',
        'bundled_files': sum(p.is_file() for p in assets.rglob('*')),
        'library': json.loads((assets / 'web/build-info.json').read_text(encoding='utf-8'))}
    (OUT / 'build-info.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    print(json.dumps(info, indent=2))
    print(f'APK ready: {apk}')


if __name__ == '__main__':
    main()
