# PyInstaller recipe for the standalone TorqueDoc.exe. Run build-exe.bat on Windows (not needed to use TorqueDoc).
from PyInstaller.utils.hooks import collect_submodules

UI = ["index.html", "app.js", "icons.js", "styles.css", "technical.js", "technical.css", "library.js",
      "library.css", "mvp.js", "mvp.css", "icon.svg", "manifest.webmanifest", "sw.js"]

hidden = ["backend.app", "backend.store", "backend.inference", "backend.web", "multipart", "python_multipart"]
hidden += collect_submodules("uvicorn")
try:
    import webview  # noqa: F401  (Windows app window; optional when building elsewhere)
    hidden += ["webview", "webview.platforms.winforms", "webview.platforms.edgechromium"]
except ImportError:
    pass

a = Analysis(
    ["desktop.py"],
    pathex=["."],
    datas=[(name, ".") for name in UI],
    hiddenimports=hidden,
    excludes=["tkinter", "pytest", "playwright", "httpx", "httpx2"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TorqueDoc", icon="torquedoc.ico",
          console=False, upx=False, version="tools/exe-version.txt")
coll = COLLECT(exe, a.binaries, a.datas, name="TorqueDoc", upx=False)
