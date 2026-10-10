"""Preview the built website on this computer: python website/preview.py  (or double-click preview-website.bat).
Phones on the same Wi-Fi can open the address it prints, but offline mode and the AI need a secure (https) site,
so for phones use a real host (see README.md, "Website")."""
import functools
import os
import socket
import sys
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DIST = Path(__file__).resolve().parent / "dist"


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".mjs": "text/javascript", ".js": "text/javascript",
                      ".wasm": "application/wasm", ".webmanifest": "application/manifest+json"}

    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, *args):
        pass


def main():
    if not (DIST / "index.html").is_file():
        raise SystemExit("Build the website first: double-click build-website.bat (or python website/build.py).")
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Handler, directory=str(DIST)))
    url = f"http://127.0.0.1:{port}/"
    print(f"TorqueDoc website preview: {url}\nClose this window to stop.")
    if os.environ.get("TORQUEDOC_NO_BROWSER") != "1":
        threading.Timer(1, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
