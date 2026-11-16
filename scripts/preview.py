#!/usr/bin/env python3
"""Preview the website locally, refreshing browsers when site files change."""

import argparse
import hashlib
import io
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent.parent
WATCHED_EXTENSIONS = {
    ".html", ".css", ".js", ".json", ".md", ".yml", ".svg", ".png",
    ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".woff", ".woff2",
}


def revision():
    state = hashlib.sha256()
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if path.suffix.lower() not in WATCHED_EXTENSIONS:
            continue
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        state.update(f"{relative}:{stat.st_mtime_ns}:{stat.st_size}\n".encode())
    return state.hexdigest()


def refresh_script(current_revision):
    return """<script>
(() => {
  const initialRevision = %s;
  const scrollKey = 'local-preview-scroll:' + location.pathname + location.search;
  try {
    const saved = sessionStorage.getItem(scrollKey);
    if (saved !== null) {
      sessionStorage.removeItem(scrollKey);
      addEventListener('load', () => scrollTo(0, Number(saved)), { once: true });
    }
  } catch (_) {}
  async function checkForChanges() {
    try {
      const response = await fetch('/__preview__/revision', { cache: 'no-store' });
      if (response.ok && (await response.json()).revision !== initialRevision) {
        try { sessionStorage.setItem(scrollKey, String(scrollY)); } catch (_) {}
        location.reload();
        return;
      }
    } catch (_) {}
    setTimeout(checkForChanges, 1000);
  }
  setTimeout(checkForChanges, 1000);
})();
</script>""" % json.dumps(current_revision)


class PreviewHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_head(self):
        if urlsplit(self.path).path == "/__preview__/revision":
            data = json.dumps({"revision": revision()}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return io.BytesIO(data)

        path = Path(self.translate_path(self.path))
        if path.is_dir() and urlsplit(self.path).path.endswith("/"):
            path = path / "index.html"
        if path.is_file() and path.suffix.lower() == ".html":
            current_revision = revision()
            html = path.read_text(encoding="utf-8")
            script = refresh_script(current_revision)
            body_end = html.lower().rfind("</body>")
            if body_end >= 0:
                html = html[:body_end] + script + html[body_end:]
            else:
                html += script
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return io.BytesIO(data)
        # Prevent conditional asset responses from retaining an old image or CSS.
        if "If-Modified-Since" in self.headers:
            del self.headers["If-Modified-Since"]
        return super().send_head()

    def log_message(self, fmt, *args):
        if urlsplit(self.path).path != "/__preview__/revision":
            super().log_message(fmt, *args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    handler = partial(PreviewHandler, directory=str(ROOT))
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Local preview: http://127.0.0.1:{server.server_port}", flush=True)
        print("Save a site file to refresh the page automatically. Ctrl+C stops the server.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
