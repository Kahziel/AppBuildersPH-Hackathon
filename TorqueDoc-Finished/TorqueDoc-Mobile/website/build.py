"""Build the TorqueDoc website into website/dist. Needs only the TorqueDoc Python environment.

The website is the same TorqueDoc interface, answering its own requests in the browser:
the built-in library is indexed here (same search database as the desktop app), and the
browser searches it, draws original PDF pages and keeps everything offline after the first visit.
Usage:  python website/build.py      (or double-click build-website.bat)
"""
import hashlib
import os
import stat
import json
import shutil
import sys
from pathlib import Path

WEBSITE = Path(__file__).resolve().parent
ROOT = WEBSITE.parent
DIST = WEBSITE / "dist"
UI = ["app.js", "icons.js", "styles.css", "technical.js", "technical.css", "library.js", "library.css", "mvp.js", "mvp.css", "icon.svg"]

sys.path.insert(0, str(WEBSITE / "scripts"))
import build_library_db  # noqa: E402


def page_html():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    replacements = [
        ("<body>", '<body class="is-web">'),
        ('<link rel="manifest" href="./manifest.webmanifest" />',
         '<link rel="manifest" href="./manifest.webmanifest" />\n    <link rel="apple-touch-icon" href="./apple-touch-icon.png" />\n'
         '    <meta name="apple-mobile-web-app-capable" content="yes" />\n    <link rel="stylesheet" href="./web/web.css" />'),
        ('<script type="module" src="./app.js"></script>',
         '<script type="module" src="./web/web.js"></script>\n    <script type="module" src="./app.js"></script>'),
    ]
    for old, new in replacements:
        if old not in html:
            raise SystemExit(f"index.html changed; could not apply: {old}")
        html = html.replace(old, new)
    return html


def vendor_folder():
    """The browser libraries (SQLite, pdf.js, wllama) ship as vendor.zip and are unpacked on first build."""
    folder = WEBSITE / "vendor"
    if not (folder / "sqlite" / "index.mjs").is_file():
        import zipfile
        with zipfile.ZipFile(WEBSITE / "vendor.zip") as archive:
            archive.extractall(folder)
    return folder


def main():
    if DIST.exists():
        if DIST.resolve().parent != WEBSITE.resolve():
            raise RuntimeError('Refusing to clean a build directory outside website/')
        def retry_readonly(function, path, error):
            os.chmod(path, stat.S_IWRITE)
            function(path)
        shutil.rmtree(DIST, onexc=retry_readonly)
    DIST.mkdir(parents=True)
    for name in UI:
        shutil.copy2(ROOT / name, DIST / name)
    (DIST / "index.html").write_text(page_html(), encoding="utf-8")
    shutil.copytree(WEBSITE / "src", DIST / "web")
    shutil.copytree(vendor_folder(), DIST / "vendor")
    for icon in (WEBSITE / "assets").iterdir():
        shutil.copy2(icon, DIST / icon.name)
    manifest = {"name": "TorqueDoc — Field workspace", "short_name": "TorqueDoc", "description": "Offline technical manuals for heavy-equipment technicians",
                "start_url": "./", "scope": "./", "display": "standalone", "orientation": "any",
                "background_color": "#0c0e11", "theme_color": "#0c0e11",
                "icons": [{"src": "./icon-192.png", "sizes": "192x192", "type": "image/png"},
                          {"src": "./icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
                          {"src": "./icon.svg", "sizes": "any", "type": "image/svg+xml"}]}
    (DIST / "manifest.webmanifest").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # The built-in library: PDFs (for page images) and the prebuilt search database.
    library = ROOT / "library"
    pdfs = sorted(p for p in library.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    for pdf in pdfs:
        target = DIST / "library" / pdf.relative_to(library)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf, target)
    build_library_db.main(DIST / "library.db", DIST / "web" / "build-info.json")

    # Hosts that support it (Netlify, Cloudflare Pages) get the headers the experimental AI needs for several cores;
    # the service worker adds the same headers everywhere else after the first visit.
    (DIST / "_headers").write_text("/*\n  Cross-Origin-Opener-Policy: same-origin\n  Cross-Origin-Embedder-Policy: require-corp\n", encoding="utf-8")
    (DIST / ".nojekyll").write_text("", encoding="utf-8")  # GitHub Pages: serve files as they are

    # Offline cache: every file of this build, under a name that changes whenever any file changes.
    files = sorted(p.relative_to(DIST).as_posix() for p in DIST.rglob("*")
                   if p.is_file() and p.name not in {"_headers", ".nojekyll"})
    digest = hashlib.sha256()
    for name in files:
        digest.update(name.encode())
        digest.update((DIST / name).read_bytes())
    template = (WEBSITE / "sw-template.js").read_text(encoding="utf-8")
    sw = template.replace("__VERSION__", digest.hexdigest()[:12]).replace("__FILES__", json.dumps(["./"] + [f"./{f}" for f in files], indent=0))
    (DIST / "sw.js").write_text(sw, encoding="utf-8")
    size = sum((DIST / f).stat().st_size for f in files)
    print(f"Website ready in {DIST}  ({len(files)} files, {size / 1e6:.1f} MB, {len(pdfs)} library PDFs)")


if __name__ == "__main__":
    main()
