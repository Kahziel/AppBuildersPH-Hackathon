"""Build the separate Android acceptance-test APK using the app's SDK and development key."""
import os
from pathlib import Path
import runpy
import zipfile

cfg = runpy.run_path(str(Path(__file__).with_name('build-android.py')))
ROOT, TOOLS, ANDROID, BUILD, SUFFIX, run, java_executable = (
    cfg[k] for k in ['ROOT', 'TOOLS', 'ANDROID', 'BUILD', 'SUFFIX', 'run', 'java_executable'])
java = java_executable()
if not java:
    raise SystemExit('Java 17+ is required.')
BUILD.mkdir(parents=True)
classes, dex = BUILD / 'classes', BUILD / 'dex'
classes.mkdir(); dex.mkdir()
run(TOOLS / ('aapt2' + SUFFIX), 'link', '-o', BUILD / 'resources.apk', '-I', ANDROID,
    '--manifest', ROOT / 'android-tests/AndroidManifest.xml', '-A', ROOT / 'android-tests/assets')
compiler = [java_executable('javac')] if java_executable('javac') else [java, 'com.sun.tools.javac.Main']
run(*compiler, '--release', '8', '-encoding', 'UTF-8', '-classpath', ANDROID, '-d', classes,
    *sorted((ROOT / 'android-tests/src').rglob('*.java')))
with zipfile.ZipFile(BUILD / 'classes.jar', 'w', zipfile.ZIP_DEFLATED) as archive:
    for file in sorted(classes.rglob('*.class')):
        archive.write(file, file.relative_to(classes).as_posix())
run(java, '-cp', TOOLS / 'lib/d8.jar', 'com.android.tools.r8.D8', '--lib', ANDROID,
    '--min-api', '28', '--output', dex, BUILD / 'classes.jar')
with zipfile.ZipFile(BUILD / 'resources.apk') as source, zipfile.ZipFile(BUILD / 'unsigned.apk', 'w', zipfile.ZIP_DEFLATED) as target:
    for info in source.infolist():
        target.writestr(info, source.read(info.filename), compress_type=zipfile.ZIP_STORED if info.filename == 'resources.arsc' else info.compress_type)
    target.write(dex / 'classes.dex', 'classes.dex')
run(TOOLS / ('zipalign' + SUFFIX), '-f', '4', BUILD / 'unsigned.apk', BUILD / 'aligned.apk')
key = Path(os.environ.get('TORQUEDOC_KEYSTORE', ROOT / '.signing/torquedoc-development.jks'))
if not key.is_file():
    raise SystemExit('Build the application first; its development signing key is required for instrumentation.')
run(java, '-jar', TOOLS / 'lib/apksigner.jar', 'sign', '--ks', key,
    '--ks-key-alias', 'torquedoc-development', '--ks-pass', 'pass:android', '--key-pass', 'pass:android',
    '--out', ROOT / 'output/TorqueDoc-tests.apk', BUILD / 'aligned.apk')
