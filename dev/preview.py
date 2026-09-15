#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["jinja2>=3.1", "watchfiles>=1.0"]
# ///
"""Local preview server for Docverse template sets.

Renders each template set's dashboard and 404 templates against the mock
scenarios in ``dev/mocks/*.toml``, mirroring Docverse's asset inlining and
edition grouping so the preview matches what Docverse publishes. A file
watcher pushes reload events to open pages over Server-Sent Events, so
the browser reloads as soon as a template, asset, or mock changes.

Run with ``npm run preview`` or ``uv run dev/preview.py``.
"""

from __future__ import annotations

import argparse
import base64
import enum
import queue
import re
import sys
import threading
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from watchfiles import watch

REPO_ROOT = Path(__file__).resolve().parent.parent
MOCKS_DIR = REPO_ROOT / "dev" / "mocks"
MAIN_SLUG = "__main"

# ---------------------------------------------------------------------------
# Context model (mirrors docverse_server.domain.dashboard_context)


class EditionKind(enum.StrEnum):
    main = "main"
    release = "release"
    draft = "draft"
    major = "major"
    minor = "minor"
    alternate = "alternate"


@dataclass(frozen=True)
class OrgContext:
    slug: str
    title: str
    base_domain: str


@dataclass(frozen=True)
class ProjectContext:
    slug: str
    title: str
    source_repo_url: str
    published_url: str


@dataclass(frozen=True)
class BuildContext:
    slug: str
    git_ref: str
    date: datetime


@dataclass(frozen=True)
class EditionContext:
    slug: str
    title: str
    kind: EditionKind
    alternate_name: str | None
    date_updated: datetime
    published_url: str
    build: BuildContext | None


@dataclass(frozen=True)
class EditionsContext:
    main: EditionContext | None
    releases: list[EditionContext] = field(default_factory=list)
    drafts: list[EditionContext] = field(default_factory=list)
    major: list[EditionContext] = field(default_factory=list)
    minor: list[EditionContext] = field(default_factory=list)
    alternates: list[EditionContext] = field(default_factory=list)


@dataclass(frozen=True)
class AssetsContext:
    css: str = ""
    js: str = ""
    images: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DocverseContext:
    api_url: str
    version: str


_VERSION_PREFIX = re.compile(r"^v?(\d+(?:\.\d+){0,2})")


def _version_key(edition: EditionContext) -> tuple[int, ...]:
    match = _VERSION_PREFIX.match(edition.slug)
    if match is None:
        return (-1,)
    return tuple(int(p) for p in match.group(1).split("."))


def _release_key(edition: EditionContext) -> tuple[int, ...]:
    key = _version_key(edition)
    return key + (0,) * (4 - len(key)) if key != (-1,) else (-1, 0, 0, 0)


def group_editions(editions: list[EditionContext]) -> EditionsContext:
    """Group and sort editions exactly as Docverse's context builder does."""
    groups: dict[EditionKind, list[EditionContext]] = {k: [] for k in EditionKind}
    main = None
    for e in editions:
        if e.slug == MAIN_SLUG:
            main = e
        else:
            groups[e.kind].append(e)
    releases = sorted(groups[EditionKind.release], key=_release_key, reverse=True)
    drafts = sorted(groups[EditionKind.draft], key=lambda e: e.date_updated, reverse=True)
    major = sorted(groups[EditionKind.major], key=_version_key, reverse=True)
    minor = sorted(groups[EditionKind.minor], key=_version_key, reverse=True)
    alternates = sorted(groups[EditionKind.alternate], key=lambda e: e.title)
    return EditionsContext(main, releases, drafts, major, minor, alternates)


# ---------------------------------------------------------------------------
# Mock scenarios


@dataclass(frozen=True)
class Scenario:
    slug: str
    title: str
    org: OrgContext
    project: ProjectContext
    editions: EditionsContext


def _as_utc(value: Any) -> datetime:
    if not isinstance(value, datetime):
        msg = f"Expected a datetime, got {value!r}"
        raise TypeError(msg)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def load_scenario(path: Path) -> Scenario:
    data = tomllib.loads(path.read_text())
    project = ProjectContext(**data["project"])
    editions = []
    for i, e in enumerate(data.get("editions", [])):
        build = None
        if "build" in e:
            build = BuildContext(
                slug=f"b{i + 1:04d}",
                git_ref=e["build"]["git_ref"],
                date=_as_utc(e["build"]["date"]),
            )
        slug = e["slug"]
        url = project.published_url if slug == MAIN_SLUG else f"{project.published_url}v/{slug}/"
        editions.append(
            EditionContext(
                slug=slug,
                title=e["title"],
                kind=EditionKind(e["kind"]),
                alternate_name=e.get("alternate_name"),
                date_updated=_as_utc(e["date_updated"]),
                published_url=url,
                build=build,
            )
        )
    return Scenario(
        slug=path.stem,
        title=data.get("title", path.stem),
        org=OrgContext(**data["org"]),
        project=project,
        editions=group_editions(editions),
    )


def load_scenarios() -> dict[str, Scenario]:
    return {p.stem: load_scenario(p) for p in sorted(MOCKS_DIR.glob("*.toml"))}


# ---------------------------------------------------------------------------
# Template sets and asset inlining (mirrors services/dashboard/asset_inliner)

_RASTER_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _image_key(path: str) -> str:
    return PurePosixPath(path).name.replace(".", "_").replace("-", "_")


def inline_assets(root: Path, section: dict[str, Any]) -> AssetsContext:
    assets = section.get("assets", {})
    css = "\n".join((root / p).read_text() for p in assets.get("css", []))
    js = "\n".join((root / p).read_text() for p in assets.get("js", []))
    images: dict[str, str] = {}
    for p in assets.get("images", []):
        ext = PurePosixPath(p).suffix.lower()
        data = (root / p).read_bytes()
        if ext == ".svg":
            images[_image_key(p)] = data.decode()
        elif ext in _RASTER_MIME:
            b64 = base64.b64encode(data).decode("ascii")
            images[_image_key(p)] = f"data:{_RASTER_MIME[ext]};base64,{b64}"
        else:
            msg = f"Unsupported image extension {ext!r} for asset {p!r}"
            raise ValueError(msg)
    return AssetsContext(css=css, js=js, images=images)


def find_template_sets() -> dict[str, Path]:
    return {
        p.name: p
        for p in sorted(REPO_ROOT.iterdir())
        if p.is_dir() and (p / "template.toml").is_file()
    }


def render_page(set_dir: Path, page: str, scenario: Scenario) -> str:
    config = tomllib.loads((set_dir / "template.toml").read_text())
    section_name = "dashboard" if page == "dashboard" else "error_404"
    section = config.get(section_name)
    if section is None:
        msg = f"{set_dir.name}/template.toml has no [{section_name}] section"
        raise LookupError(msg)
    env = Environment(
        loader=FileSystemLoader(set_dir),
        undefined=StrictUndefined,
        autoescape=True,
    )
    template = env.get_template(section["template"])
    return template.render(
        org=scenario.org,
        project=scenario.project,
        editions=scenario.editions,
        assets=inline_assets(set_dir, section),
        docverse=DocverseContext(api_url="http://localhost:8080/docverse", version="dev"),
        rendered_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# HTTP server with live reload


class ReloadBroker:
    """Fan out file-change notifications to connected SSE clients."""

    def __init__(self) -> None:
        self._subscribers: set[queue.SimpleQueue[str]] = set()
        self._lock = threading.Lock()
        self.stop_event = threading.Event()

    def subscribe(self) -> queue.SimpleQueue[str]:
        q: queue.SimpleQueue[str] = queue.SimpleQueue()
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.SimpleQueue[str]) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def publish(self, message: str) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            q.put(message)

    def watch_forever(self) -> None:
        """Watch preview inputs and publish a reload on every change.

        Runs in a daemon thread. Template sets added after startup are not
        watched until the server restarts.
        """
        roots = [*find_template_sets().values(), MOCKS_DIR, Path(__file__)]
        for changes in watch(*roots, stop_event=self.stop_event):
            paths = sorted({Path(path).relative_to(REPO_ROOT).as_posix() for _, path in changes})
            sys.stderr.write(f"changed: {', '.join(paths)}\n")
            self.publish(paths[0])


BROKER = ReloadBroker()


LIVE_RELOAD_JS = """
<script data-docverse-preview>
(function () {
  var source = new EventSource("/__events");
  var lostConnection = false;
  source.addEventListener("reload", function () { location.reload(); });
  source.onerror = function () { lostConnection = true; };
  source.onopen = function () {
    // Reconnected after a server restart: the script itself may have changed.
    if (lostConnection) { location.reload(); }
  };
})();
</script>
"""


def with_live_reload(html: str) -> str:
    if "</body>" in html:
        return html.replace("</body>", LIVE_RELOAD_JS + "</body>", 1)
    return html + LIVE_RELOAD_JS


def index_page(sets: dict[str, Path], scenarios: dict[str, Scenario]) -> str:
    parts = [
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>",
        "<title>Docverse template preview</title>",
        "<style>body{font-family:system-ui,sans-serif;max-width:48rem;margin:2rem auto;padding:0 1rem;line-height:1.5}",
        "table{border-collapse:collapse}td,th{padding:.3rem .8rem;text-align:left;border-bottom:1px solid #ddd}</style>",
        "</head><body><h1>Docverse template preview</h1>",
    ]
    for name in sets:
        parts.append(f"<h2>{escape(name)}</h2><table><tr><th>Scenario</th><th>Dashboard</th><th>404</th></tr>")
        for slug, sc in scenarios.items():
            parts.append(
                f"<tr><td>{escape(sc.title)}</td>"
                f"<td><a href='/{escape(name)}/dashboard/{escape(slug)}/'>dashboard</a></td>"
                f"<td><a href='/{escape(name)}/404/{escape(slug)}/'>404</a></td></tr>"
            )
        parts.append("</table>")
    parts.append("</body></html>")
    return "".join(parts)


def error_page(status: HTTPStatus, message: str) -> str:
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{status.value} {escape(status.phrase)}</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:48rem;margin:2rem auto;padding:0 1rem}"
        "pre{white-space:pre-wrap;background:#f5f5f5;padding:1rem}</style></head>"
        f"<body><h1>{status.value} {escape(status.phrase)}</h1><pre>{escape(message)}</pre>"
        "<p><a href='/'>Back to index</a></p></body></html>"
    )


class PreviewHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # quieter logging
        if self.path != "/__events":
            sys.stderr.write(f"{self.address_string()} {fmt % args}\n")

    def _serve_events(self) -> None:
        """Hold an SSE connection open and push reload events."""
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = BROKER.subscribe()
        try:
            self.wfile.write(b"retry: 1000\n\n")
            self.wfile.flush()
            while True:
                try:
                    changed = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": keep-alive\n\n")  # comment line, ignored by clients
                else:
                    self.wfile.write(f"event: reload\ndata: {changed}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # client navigated away or reloaded
        finally:
            BROKER.unsubscribe(q)

    def _send(self, status: HTTPStatus, body: str, content_type: str = "text/html; charset=utf-8") -> None:
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/__events":
            self._serve_events()
            return
        try:
            sets = find_template_sets()
            scenarios = load_scenarios()
            if path == "/":
                self._send(HTTPStatus.OK, with_live_reload(index_page(sets, scenarios)))
                return
            parts = [p for p in path.split("/") if p]
            if len(parts) != 3 or parts[1] not in ("dashboard", "404"):
                self._send(HTTPStatus.NOT_FOUND, error_page(HTTPStatus.NOT_FOUND, f"No route for {path}"))
                return
            set_name, page, scenario_slug = parts
            if set_name not in sets:
                self._send(HTTPStatus.NOT_FOUND, error_page(HTTPStatus.NOT_FOUND, f"Unknown template set {set_name!r}"))
                return
            if scenario_slug not in scenarios:
                self._send(HTTPStatus.NOT_FOUND, error_page(HTTPStatus.NOT_FOUND, f"Unknown scenario {scenario_slug!r}"))
                return
            html = render_page(sets[set_name], page, scenarios[scenario_slug])
            self._send(HTTPStatus.OK, with_live_reload(html))
        except Exception as exc:  # show render errors in the browser
            import traceback

            self._send(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                with_live_reload(error_page(HTTPStatus.INTERNAL_SERVER_ERROR, traceback.format_exc() or str(exc))),
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), PreviewHandler)
    server.daemon_threads = True  # don't wait on open SSE connections at exit
    threading.Thread(target=BROKER.watch_forever, name="watcher", daemon=True).start()
    print(f"Docverse template preview: http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        BROKER.stop_event.set()
        server.server_close()


if __name__ == "__main__":
    main()
