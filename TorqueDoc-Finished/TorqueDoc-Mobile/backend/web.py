"""Save public web pages as offline, citable PDF snapshots.

This is the only part of TorqueDoc that uses the internet, and only when someone asks it to:
adding a web page in the app, or downloading the web sources listed in library/catalog.json.
After saving, a snapshot is searched and viewed offline like any manual.
"""
from __future__ import annotations

import html
import io
import ipaddress
import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import pymupdf

MAX_WEB_BYTES = 8 * 1024 * 1024
MIN_TEXT = 200
USER_AGENT = "TorqueDoc/1.3 (offline reference snapshot)"
WARNING = ("WEB SOURCE — not an OEM service manual. Information from websites can be incomplete, "
           "outdated or wrong. Verify it against the manufacturer's documentation before any maintenance.")


class WebError(ValueError):
    pass


# ---- fetching ---------------------------------------------------------------------------------
def check_url(url, allow_private=False):
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise WebError("Enter a full web address starting with https:// or http://.")
    if parsed.username or parsed.password:
        raise WebError("Web addresses with a user name or password are not supported.")
    if not allow_private:
        try:
            addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
        except socket.gaierror as exc:
            raise WebError("That website could not be found. Check the address and your internet connection.") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address.split("%")[0])
            if not ip.is_global:
                raise WebError("Only public websites can be saved, not addresses on this computer or local network.")
    return parsed.geturl()


class CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, allow_private):
        self.allow_private = allow_private

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl, self.allow_private)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, allow_private=False, timeout=30):
    """Return (bytes, content_type, charset, final_url)."""
    url = check_url(url, allow_private)
    opener = urllib.request.build_opener(CheckedRedirect(allow_private))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5"})
    try:
        with opener.open(request, timeout=timeout) as response:
            content = response.read(MAX_WEB_BYTES + 1)
            content_type = response.headers.get_content_type()
            charset = response.headers.get_content_charset() or "utf-8"
            final = response.geturl()
    except WebError:
        raise
    except urllib.error.HTTPError as exc:
        raise WebError(f"The website answered with error {exc.code}. The page may have moved or need a login.") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise WebError("The website could not be reached. Saving a web page needs an internet connection.") from exc
    if len(content) > MAX_WEB_BYTES:
        raise WebError("That page is larger than 8 MB.")
    return content, content_type, charset, final


# ---- HTML to a clean, printable snapshot ------------------------------------------------------
SKIP = {"script", "style", "noscript", "template", "svg", "canvas", "iframe", "object", "embed", "nav", "footer",
        "header", "aside", "form", "button", "select", "textarea", "input", "head", "title", "dialog", "menu"}
KEEP = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "li", "table", "thead", "tbody", "tfoot", "tr", "th",
        "td", "caption", "pre", "code", "b", "strong", "i", "em", "blockquote", "dl", "dt", "dd", "sup", "sub", "div"}
BLOCKS = {"section": "div", "article": "div", "main": "div", "figure": "div", "figcaption": "p"}
VOID = {"br", "hr", "img", "meta", "link", "input", "wbr", "source", "area", "col", "base", "param", "track"}


class Cleaner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.skip, self.title, self.in_title, self.alts = [], [], 0, "", False, set()

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        if tag in VOID:
            if not self.skip and tag == "br":
                self.out.append("<br/>")
            elif not self.skip and tag == "img":
                alt = (dict(attrs).get("alt") or "").strip()
                if alt and alt not in self.alts:  # galleries repeat the same caption
                    self.alts.add(alt)
                    self.out.append(f"<i>[image: {html.escape(alt)}]</i>")
            return
        if self.skip or tag in SKIP:
            self.skip += 1
            self.stack.append(("skip", tag))
            return
        mapped = BLOCKS.get(tag, tag if tag in KEEP else None)
        span = dict(attrs).get("colspan") if tag in {"td", "th"} else None
        if mapped:
            self.out.append(f'<{mapped} colspan="{int(span)}">' if span and span.isdigit() else f"<{mapped}>")
        self.stack.append((mapped, tag))

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in VOID:
            return
        # Close up to the matching start tag; tolerate sloppy HTML.
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][1] == tag:
                for mapped, _ in reversed(self.stack[index:]):
                    if mapped == "skip":
                        self.skip -= 1
                    elif mapped:
                        self.out.append(f"</{mapped}>")
                del self.stack[index:]
                return

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif not self.skip and data.strip():
            self.out.append(html.escape(re.sub(r"\s+", " ", data)))

    def result(self):
        for mapped, _ in reversed(self.stack):
            if mapped and mapped != "skip":
                self.out.append(f"</{mapped}>")
        return "".join(self.out), re.sub(r"\s+", " ", self.title).strip()


CSS = """
body { font-family: sans-serif; font-size: 10pt; line-height: 1.35; }
h1 { font-size: 16pt; } h2 { font-size: 13pt; } h3 { font-size: 11.5pt; } h4, h5, h6 { font-size: 10.5pt; }
table { border-collapse: collapse; margin: 4pt 0; } th, td { border: 0.5pt solid #999; padding: 2pt 4pt; vertical-align: top; }
th { background-color: #eee; } pre { font-family: monospace; font-size: 8.5pt; }
.source { border: 1pt solid #b06a00; background-color: #fff4e0; padding: 6pt; margin-bottom: 10pt; font-size: 9pt; }
"""


def render_pdf(body_html, title, url, saved):
    header = (f'<div class="source"><p><b>{html.escape(WARNING)}</b></p>'
              f"<p>Page title: {html.escape(title)}<br/>Web address: {html.escape(url)}<br/>Saved for offline use: {saved}</p></div>")
    story = pymupdf.Story(html=header + body_html, user_css=CSS)
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    box = pymupdf.paper_rect("a4")
    more, pages = 1, 0
    while more:
        device = writer.begin_page(box)
        more, _ = story.place(box + (42, 42, -42, -42))
        story.draw(device)
        writer.end_page()
        pages += 1
        if pages > 400:
            break
    writer.close()
    with pymupdf.open(stream=buffer.getvalue(), filetype="pdf") as pdf:
        pdf.set_metadata({"title": title[:200], "subject": f"Web snapshot of {url} saved {saved}", "creator": "TorqueDoc"})
        return pdf.tobytes(garbage=3, deflate=True)


def snapshot(content, content_type, charset, url, saved=None):
    """Return (pdf_bytes, page_title). PDFs from the web are kept as they are."""
    saved = saved or date.today().isoformat()
    if content_type == "application/pdf" or content[:5] == b"%PDF-":
        return content, Path(urllib.parse.urlparse(url).path).name or url
    if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
        raise WebError(f"This address returns {content_type}, not a web page or PDF.")
    try:
        text = content.decode(charset, errors="replace")
    except LookupError:
        text = content.decode("utf-8", errors="replace")
    if content_type == "text/plain":
        body, title = f"<pre>{html.escape(text)}</pre>", url
    else:
        cleaner = Cleaner()
        cleaner.feed(text)
        body, title = cleaner.result()
    if len(re.sub(r"<[^>]+>|\s", "", body)) < MIN_TEXT:
        raise WebError("This page has almost no readable text. It may need JavaScript or a login. "
                       "Try the site's printable page or PDF brochure instead.")
    title = title or urllib.parse.urlparse(url).hostname
    return render_pdf(body, title, url, saved), title


def save_page(url, allow_private=False, fetcher=None):
    """Download a page and return (pdf_bytes, title, final_url)."""
    content, content_type, charset, final = (fetcher or fetch)(url, allow_private)
    pdf, title = snapshot(content, content_type, charset, final)
    return pdf, title, final


# ---- built-in web sources listed in library/catalog.json --------------------------------------
def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "page"


def download_library_sources(library, fetcher=None, progress=None, only_missing=False):
    """Save every catalog "web_sources" entry to library/<machine>/web/ and describe it in the catalog.
    Returns a list of error messages. Requires internet; existing snapshots are kept when a download fails."""
    library = Path(library)
    path = library / "catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
    sources = [s for s in catalog.get("web_sources") or [] if isinstance(s, dict) and s.get("url") and s.get("machine")]
    documents = [d for d in catalog.get("documents") or [] if isinstance(d, dict)]
    errors = []
    for index, source in enumerate(sources):
        if progress:
            progress(index, len(sources), source["url"])
        machine = str(source["machine"])
        if not re.match(r"^[a-z0-9][a-z0-9_-]{0,39}$", machine):
            errors.append(f"{source['url']}: invalid machine id {machine!r}")
            continue
        relative = f"{machine}/web/{slug(source.get('file') or source.get('title') or urllib.parse.urlparse(source['url']).path)}.pdf"
        target = library / relative
        if only_missing and target.is_file():
            continue
        try:
            pdf, title, final = save_page(source["url"], fetcher=fetcher)
        except (WebError, RuntimeError, ValueError) as exc:
            errors.append(f"{source['url']}: {exc}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(".tmp")
        partial.write_bytes(pdf)
        partial.replace(target)
        entry = {"file": relative, "title": source.get("title") or title,
                 "variant": source.get("variant") or "See web page", "revision": f"Web page saved {date.today().isoformat()}",
                 "type": "web", "url": final}
        documents = [d for d in documents if str(d.get("file", "")).replace("\\", "/").lower() != relative.lower()] + [entry]
    if progress:
        progress(len(sources), len(sources), "")
    if documents == [d for d in catalog.get("documents") or [] if isinstance(d, dict)]:
        return errors  # Nothing new was saved: leave catalog.json untouched.
    catalog["documents"] = documents
    partial = path.with_suffix(".tmp")
    partial.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    partial.replace(path)
    return errors


def listed_sources(library):
    try:
        catalog = json.loads((Path(library) / "catalog.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return 0, 0
    sources = [s for s in catalog.get("web_sources") or [] if isinstance(s, dict) and s.get("url")]
    saved = sum((Path(library) / f"{s.get('machine')}/web/{slug(s.get('file') or s.get('title') or urllib.parse.urlparse(s['url']).path)}.pdf").is_file() for s in sources)
    return len(sources), saved


if __name__ == "__main__":
    # python -m backend.web  -> download all web sources listed in library/catalog.json (internet needed)
    root = Path(__file__).resolve().parent.parent / "library"
    failures = download_library_sources(root, progress=lambda i, n, u: u and print(f"[{i + 1}/{n}] {u}"))
    for failure in failures:
        print("FAILED:", failure)
    print("Done." if not failures else f"Done with {len(failures)} problem(s).")
    sys.exit(1 if failures else 0)
