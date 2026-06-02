#!/usr/bin/env python3
"""sectormap live server — the dashboard arm of the PRD.

Serves the dashboard + the graph JSON, and PUSHES to the browser when any repo
file changes (Server-Sent Events). The "watcher" is a stdlib mtime poll — no deps,
genuinely live: edit a file, the dashboard re-renders within ~1s.

    python3 server.py [--port 8765]   then open the printed URL.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKIP = {".git", "__pycache__", "node_modules", "build", "dist", "DerivedData", ".gradle"}

# Set in main() from env/args. Default: map owlspace_map (this repo).
REPO = HERE.parent
PROFILE = None
CALL_GRAPH = None  # override the call-graph provider (e.g. "graphify")
WATCH = HERE.parent          # the subtree the watcher polls (src dir for big repos)
_VERSION = 0                 # bumped by the watcher whenever WATCH changes


def _signature() -> float:
    """Newest mtime across the watched subtree — cheap change-detector."""
    newest = 0.0
    for p in WATCH.rglob("*"):
        if any(part in SKIP for part in p.parts):
            continue
        try:
            if p.is_file():
                newest = max(newest, p.stat().st_mtime)
        except OSError:
            pass
    return newest


def _watch():
    global _VERSION
    last = _signature()
    while True:
        time.sleep(1.0)
        try:
            sig = _signature()
        except OSError:
            continue
        if sig != last:
            last = sig
            _VERSION += 1  # a real file changed → tell every browser to re-render


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, ctype, body: bytes, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = (HERE / "dashboard.html").read_bytes()
            self._send(200, "text/html; charset=utf-8", html)
        elif self.path.startswith("/api/graph"):
            from extract import build_graph, default_profile
            prof = PROFILE
            if CALL_GRAPH:  # inject the chosen call-graph provider
                prof = dict(PROFILE or default_profile(REPO))
                prof["call_graph"] = CALL_GRAPH
            body = json.dumps(build_graph(REPO, prof)).encode()
            self._send(200, "application/json", body, {"Cache-Control": "no-store"})
        elif self.path.startswith("/api/events"):
            self._sse()
        else:
            self._send(404, "text/plain", b"not found")

    def _sse(self):
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            last = -1
            while True:
                if _VERSION != last:
                    last = _VERSION
                    self.wfile.write(f"data: {json.dumps({'version': last})}\n\n".encode())
                    self.wfile.flush()
                else:
                    self.wfile.write(b": keepalive\n\n")  # comment frame
                    self.wfile.flush()
                time.sleep(0.7)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return  # browser navigated away


def main():
    global REPO, PROFILE, WATCH, CALL_GRAPH
    port = 8765
    a = sys.argv
    if "--port" in a:
        port = int(a[a.index("--port") + 1])
    if "--call-graph" in a:
        CALL_GRAPH = a[a.index("--call-graph") + 1]
    if "--repo" in a:
        REPO = Path(a[a.index("--repo") + 1]).resolve()
        WATCH = REPO
    if "--profile" in a:
        PROFILE = json.loads(Path(a[a.index("--profile") + 1]).read_text())
        # watch only the source subtree (big repos have huge build/Pods trees)
        if PROFILE.get("src_base"):
            WATCH = REPO / PROFILE["src_base"]
    threading.Thread(target=_watch, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    label = (PROFILE or {}).get("label", REPO.name)
    print(f"sectormap live → http://127.0.0.1:{port}   [{label}]   (watching {WATCH}, Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
