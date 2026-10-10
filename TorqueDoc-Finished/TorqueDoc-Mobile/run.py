"""Launch TorqueDoc on loopback. Keep this process running while the UI is open."""
import os
from pathlib import Path
import socket
import threading
import webbrowser

if __name__ == "__main__":
    os.environ.setdefault("OLLAMA_NO_CLOUD", "1")
    os.chdir(Path(__file__).resolve().parent)
    try:
        import uvicorn
        import pymupdf
    except ImportError:
        raise SystemExit("Dependencies missing. Run setup-windows.bat, or pip install -r requirements.txt in your virtual environment.")
    port = int(os.environ.get("PORT", "4173"))
    url = f"http://127.0.0.1:{port}"
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise SystemExit(f"Port {port} is already in use. TorqueDoc may already be running: open {url}\n"
                             "Otherwise close the other program or TorqueDoc window using this port and try again.")
    print(f"\nTorqueDoc: {url}\nKeep this window open. Ctrl+C stops the local app.\n")
    if os.environ.get("TORQUEDOC_NO_BROWSER") != "1":
        threading.Timer(2, lambda: webbrowser.open(url)).start()
    uvicorn.run("backend.app:app", host="127.0.0.1", port=port, access_log=False)
