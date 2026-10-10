"""TorqueDoc as a desktop application: a native window (Windows Edge WebView2), no browser needed.

The window opens at once with a "Starting TorqueDoc" screen while the local engine starts in this
process; the engine stops when the window is closed. If the WebView2 component is missing,
TorqueDoc falls back to opening in the default browser.
"""
import faulthandler
import html
import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FROZEN = getattr(sys, "frozen", False)  # the standalone TorqueDoc.exe built by build-exe.bat
if FROZEN:
    # Program files are unpacked inside the package; the library and your data live next to TorqueDoc.exe.
    ROOT = Path(sys.executable).resolve().parent
    os.environ.setdefault("TORQUEDOC_LIBRARY", str(ROOT / "library"))
    os.environ.setdefault("TORQUEDOC_DATA_DIR", str(ROOT / "data"))
PREFERRED_PORT = 4173  # Kept stable: notes saved in the app window belong to this exact address.
START_TIMEOUT = 120    # seconds; first starts on a busy laptop can be slow
NO_CONSOLE = sys.stdout is None  # started with pythonw.exe from TorqueDoc.exe or a shortcut
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class OlderTorqueDocRunning(RuntimeError):
    pass


def data_dir():
    return Path(os.environ.get("TORQUEDOC_DATA_DIR", ROOT / "data"))


def log(message):
    line = f"[TorqueDoc] {message}"
    if not NO_CONSOLE:
        print(line, flush=True)
    try:
        data_dir().mkdir(parents=True, exist_ok=True)
        with open(data_dir() / "torquedoc-app.log", "a", encoding="utf-8") as file:
            file.write(time.strftime("%Y-%m-%d %H:%M:%S ") + line + "\n")
    except OSError:
        pass


def message_box(text, title="TorqueDoc", error=False):
    """A plain Windows dialog when there is no console to show messages in."""
    if sys.platform == "win32" and NO_CONSOLE:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10 if error else 0x40)
        return True
    return False


def get_json(port, path, timeout):
    try:
        with OPENER.open(f"http://127.0.0.1:{port}{path}", timeout=timeout) as response:
            return json.loads(response.read())
    except Exception:
        return None


def current_torquedoc(port):
    """True when this version of TorqueDoc answers on the port (instant check, no Ollama or database)."""
    return (get_json(port, "/api/ping", 5) or {}).get("app") == "torquedoc"


def port_free(port):
    with socket.socket() as probe:
        probe.settimeout(5)
        return probe.connect_ex(("127.0.0.1", port)) != 0


def choose_port():
    """Return (port, already_running)."""
    if current_torquedoc(PREFERRED_PORT):
        return PREFERRED_PORT, True
    if port_free(PREFERRED_PORT):
        return PREFERRED_PORT, False
    # An older TorqueDoc (the black console window) answers /api/health but not /api/ping.
    if (get_json(PREFERRED_PORT, "/api/health", 15) or {}).get("backend") == "ready":
        raise OlderTorqueDocRunning(
            "An older TorqueDoc is still running in the background (a black window titled with "
            "python.exe or start-windows.bat).\n\nClose that window, or restart the computer, then open TorqueDoc again.")
    with socket.socket() as spare:
        spare.bind(("127.0.0.1", 0))
        log(f"Port {PREFERRED_PORT} is used by another program; using {spare.getsockname()[1]} for this session. "
            "Notes saved this time are kept separately until that program is closed.")
        return spare.getsockname()[1], False


def start_engine(port, progress=None):
    import uvicorn
    from backend.app import app  # imported directly so the standalone exe includes it
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True, name="torquedoc-engine")
    thread.start()
    started = time.monotonic()
    while time.monotonic() - started < START_TIMEOUT:
        if current_torquedoc(port):
            log(f"Engine ready on port {port} after {time.monotonic() - started:.1f} s.")
            return server, thread
        if not thread.is_alive():
            raise RuntimeError("The TorqueDoc engine stopped while starting. Details are in data\\torquedoc-engine.log.")
        if progress:
            progress(time.monotonic() - started)
        time.sleep(0.2)
    faulthandler.dump_traceback(file=sys.stderr)  # where it was stuck, for troubleshooting
    raise RuntimeError(f"The TorqueDoc engine did not start within {START_TIMEOUT} seconds. "
                       "Close other programs to free memory, then try again.")


class Engine:
    """Starts (or reuses) the engine once; shared by the window and the browser fallback."""

    def __init__(self):
        self.server, self.url, self.error = None, None, None
        self.lock = threading.Lock()

    def ensure(self, progress=None):
        with self.lock:
            if self.url or self.error:
                return self.url
            try:
                port, running = choose_port()
                if running:
                    log("TorqueDoc is already running; opening another window.")
                else:
                    log("Starting the local engine…")
                    self.server, _ = start_engine(port, progress)
                self.url = f"http://127.0.0.1:{port}/"
            except Exception as exc:
                log(f"Could not start: {exc}")
                self.error = exc
            return self.url

    def stop(self):
        if self.server is not None:
            self.server.should_exit = True
            log("Stopped.")


SPLASH = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;height:100%;background:#0c0e11;color:#f1f2f4;font-family:'Segoe UI',Arial,sans-serif}}
main{{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;padding:24px;text-align:center}}
.mark{{width:64px;height:64px;border-radius:16px;background:#f59e0b}} h1{{margin:0;font-size:22px}}
p{{margin:0;color:#939ba9;max-width:520px;line-height:1.5}} .error{{color:#f27474}}
.bar{{width:220px;height:4px;border-radius:2px;background:#292e36;overflow:hidden}}
.bar i{{display:block;width:40%;height:100%;background:#f5aa24;animation:m 1.2s ease-in-out infinite}}
@keyframes m{{0%{{transform:translateX(-100%)}}100%{{transform:translateX(250%)}}}}
</style></head><body><main><div class="mark"></div><h1>{title}</h1>{body}</main></body></html>"""


def splash(title, text, error=False):
    body = f'<p class="{"error" if error else ""}">{html.escape(text)}</p>' + ("" if error else '<div class="bar"><i></i></div>')
    return SPLASH.format(title=html.escape(title), body=body)


def run_window(engine, storage):
    """Return True when the app window was shown (and has now been closed); False if no window is available."""
    try:
        import webview
    except ImportError:
        log("Desktop window component (pywebview) is not installed.")
        return False
    webview.settings["ALLOW_DOWNLOADS"] = True                  # Export logs, Save a copy
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True   # Web-source links open in the normal browser
    window = webview.create_window("TorqueDoc", html=splash("Starting TorqueDoc…", "Preparing your offline manuals."),
                                   width=1360, height=900, min_size=(400, 600), background_color="#0C0E11")
    shown = threading.Event()

    def boot():
        shown.set()
        def progress(seconds):
            if seconds > 20 and int(seconds) % 5 == 0:
                window.load_html(splash("Starting TorqueDoc…", "This is taking longer than usual. "
                                        "Your computer may be busy; closing other programs helps."))
        url = engine.ensure(progress)
        if url:
            window.load_url(url)
        else:
            window.load_html(splash("TorqueDoc could not start", str(engine.error), error=True))

    try:
        storage.mkdir(parents=True, exist_ok=True)
        # private_mode=False keeps maintenance notes and settings between launches.
        webview.start(boot, gui="edgechromium" if sys.platform == "win32" else None,
                      private_mode=False, storage_path=str(storage))
        return shown.is_set()
    except Exception as exc:  # WebView2 runtime missing or unsupported system
        log(f"Desktop window could not open ({exc}).")
        return shown.is_set()


def run_browser(engine):
    url = engine.ensure()
    if not url:
        raise engine.error
    log(f"Opening TorqueDoc in your web browser instead: {url}")
    webbrowser.open(url)
    if engine.server is None:
        return
    if message_box("TorqueDoc is open in your web browser because the app window component (Microsoft Edge WebView2) "
                   "is not available on this computer.\n\nKeep this message open while you use TorqueDoc. "
                   "Click OK to stop TorqueDoc."):
        return
    log("Keep this window open while you use TorqueDoc. Close it to stop.")
    try:
        while engine.server.started and not engine.server.should_exit:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass


def main():
    os.chdir(ROOT)
    if NO_CONSOLE:
        # The engine's own messages need somewhere to go when there is no console window.
        data_dir().mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(data_dir() / "torquedoc-engine.log", "a", encoding="utf-8", buffering=1)
    os.environ.setdefault("OLLAMA_NO_CLOUD", "1")
    os.environ.setdefault("OLLAMA_HOST", "http://127.0.0.1:11434")
    try:
        import uvicorn  # noqa: F401
        import pymupdf  # noqa: F401
    except ImportError:
        if not message_box("Some TorqueDoc components are missing. "
                           + ("Download the TorqueDoc package again." if FROZEN else "Double-click Start-TorqueDoc.bat to finish setup."), error=True):
            raise SystemExit("Components missing. Double-click Start-TorqueDoc.bat to finish setup.")
        return
    engine = Engine()
    try:
        if os.environ.get("TORQUEDOC_BROWSER") == "1" or not run_window(engine, data_dir() / "app-window"):
            run_browser(engine)
    finally:
        engine.stop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"Could not start: {exc}")
        if not message_box(f"TorqueDoc could not start.\n\n{exc}\n\nDetails are in data\\torquedoc-app.log.", error=True):
            raise
