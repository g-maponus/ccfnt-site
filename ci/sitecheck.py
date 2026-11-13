"""Shared helpers for the ccfnt.org site checks (Python 3 standard library only).

A check is a module with NAME, SUMMARY and run(site) -> list[Finding].
Checks that look at "what changed" use site.changed_lines() / site.changed_files(),
which compare the working tree with the merge-base of --base and HEAD.
"""

import html.parser
import os
import posixpath
import re
import subprocess
import urllib.parse
from dataclasses import dataclass

# Server-generated content, skipped by every check until it leaves the web root
# (HOM-20): it cannot be fixed by hand here. Paths are repository-relative.
GENERATED_PREFIXES = ("messages/",)

# Our own hosts: references to them are not "outside requests".
SITE_HOSTS = frozenset({"ccfnt.org", "www.ccfnt.org"})

# Local URL paths that are not files in this repository.
NOT_IN_REPO_PREFIXES = ("/api/", "/messages/", "/cdn-cgi/")

# Schemes that never point at a file (and are never fetched by the page).
NON_FILE_SCHEMES = frozenset({"mailto", "tel", "sms", "javascript", "data", "blob", "about"})

# <link rel> values that make the browser fetch the href while loading the page.
LOADING_LINK_RELS = frozenset({
    "stylesheet", "icon", "shortcut", "apple-touch-icon", "apple-touch-icon-precomposed",
    "mask-icon", "manifest", "preload", "prefetch", "modulepreload", "preconnect",
    "dns-prefetch", "prerender",
})

# (tag, attribute) pairs whose URL the browser fetches while loading the page.
LOADING_ATTRS = frozenset({
    ("script", "src"), ("img", "src"), ("img", "srcset"), ("iframe", "src"),
    ("frame", "src"), ("embed", "src"), ("object", "data"), ("source", "src"),
    ("source", "srcset"), ("video", "src"), ("video", "poster"), ("audio", "src"),
    ("track", "src"), ("input", "src"), ("image", "href"), ("image", "xlink:href"),
    ("use", "href"), ("use", "xlink:href"),
})

# (tag, attribute) pairs that are links the visitor can follow.
LINK_ATTRS = frozenset({("a", "href"), ("area", "href"), ("form", "action")})

CSS_URL_RE = re.compile(r"""url\(\s*(['"]?)([^'")]+?)\1\s*\)|@import\s+(['"])([^'"]+)\3""", re.I)


class SiteError(Exception):
    """A problem running the checks themselves (not a finding about the site)."""


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    message: str

    def __str__(self):
        return f"{self.path}:{self.line}: {self.message}" if self.line else f"{self.path}: {self.message}"


@dataclass(frozen=True)
class Ref:
    """A URL found in a page or stylesheet."""
    line: int
    url: str
    tag: str
    loads: bool  # fetched while the page loads (script, CSS, image, iframe...)
    where: str   # e.g. "<img src>", "CSS url()"


def is_generated(path):
    return path.startswith(GENERATED_PREFIXES)


def css_refs(text, first_line=1, where="CSS url()"):
    """URLs referenced by url(...) and @import in a piece of CSS."""
    refs = []
    for m in CSS_URL_RE.finditer(text):
        url = (m.group(2) or m.group(4) or "").strip()
        line = first_line + text.count("\n", 0, m.start())
        refs.append(Ref(line, url, "", True, where if m.group(2) is not None else "CSS @import"))
    return refs


class _RefParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs = []
        self._in_style = False

    def handle_starttag(self, tag, attrs):
        line = self.getpos()[0]
        values = {name: value for name, value in attrs if value is not None}
        if tag == "style":
            self._in_style = True
        if "style" in values:
            self.refs += css_refs(values["style"], line, "style=\"url()\"")
        if tag == "link" and "href" in values:
            rels = set(values.get("rel", "").lower().split())
            self.refs.append(Ref(line, values["href"], tag, bool(rels & LOADING_LINK_RELS),
                                 f"<link rel=\"{values.get('rel', '')}\">"))
        if tag == "input" and values.get("type", "").lower() != "image":
            return
        for attr, value in values.items():
            if (tag, attr) in LOADING_ATTRS:
                urls = srcset_urls(value) if attr == "srcset" else [value]
                self.refs += [Ref(line, u, tag, True, f"<{tag} {attr}>") for u in urls]
            elif (tag, attr) in LINK_ATTRS:
                self.refs.append(Ref(line, value, tag, False, f"<{tag} {attr}>"))

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag):
        if tag == "style":
            self._in_style = False

    def handle_data(self, data):
        if self._in_style:
            self.refs += css_refs(data, self.getpos()[0], "<style> url()")


def srcset_urls(value):
    return [c.split()[0] for c in value.split(",") if c.strip()]


def html_refs(text):
    parser = _RefParser()
    parser.feed(text)
    parser.close()
    return parser.refs


def external_host(url):
    """Host name if the URL points outside the page's origin, else None."""
    url = url.strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme in ("http", "https") or url.startswith("//"):
        return (parts.hostname or "").lower()
    return None


def local_target(page_path, url):
    """Resolve a same-site URL found in page_path to a URL path such as "/messes/".

    Returns None when the URL does not point at a file in this repository:
    other hosts, mailto:/tel:/data: etc., fragment-only links, /api/, /messages/,
    /cdn-cgi/. Absolute https://ccfnt.org/... URLs are not resolved either.
    """
    url = url.strip()
    if not url or url.startswith("#") or "${" in url or "{{" in url:
        return None
    parts = urllib.parse.urlsplit(url)
    if parts.scheme or url.startswith("//"):
        return None
    path = urllib.parse.unquote(parts.path)
    if not path:
        return None  # "?x=1" or "#top": the page itself
    if not path.startswith("/"):
        path = posixpath.join("/" + posixpath.dirname(page_path), path)
    trailing_slash = path.endswith("/")
    path = "/" + posixpath.normpath(path).lstrip("/")
    if trailing_slash and path != "/":
        path += "/"
    if (path + "/").startswith(NOT_IN_REPO_PREFIXES):  # "/api" as well as "/api/x"
        return None
    return path


def query_param(url, name):
    """Value of a query parameter (e.g. ?v=3), or None if absent."""
    query = urllib.parse.urlsplit(url.strip()).query
    values = urllib.parse.parse_qs(query, keep_blank_values=True).get(name)
    return values[0] if values else None


class Site:
    """The repository under test: its files, and what changed since the base."""

    def __init__(self, root, base=None):
        self.root = os.path.abspath(root)
        self.base = base
        self._files = None
        self._merge_base = None
        self._refs = {}

    # -- git -----------------------------------------------------------------
    def git(self, *args):
        cmd = ["git", "-C", self.root, "-c", "core.quotePath=false", *args]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", "replace").strip()
            raise SiteError(f"`git {' '.join(args)}` failed: {err}")
        return result.stdout.decode("utf-8", "replace")

    @property
    def merge_base(self):
        if self._merge_base is None:
            if not self.base:
                raise SiteError("this check needs --base (e.g. --base origin/main)")
            try:
                self.git("rev-parse", "--verify", "--quiet", f"{self.base}^{{commit}}")
            except SiteError:
                raise SiteError(f"base '{self.base}' not found; run `git fetch origin main` "
                                "or pass another --base") from None
            self._merge_base = self.git("merge-base", self.base, "HEAD").strip()
        return self._merge_base

    # -- files ---------------------------------------------------------------
    @property
    def files(self):
        """Tracked plus untracked-but-not-ignored files that exist on disk."""
        if self._files is None:
            out = self.git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
            self._files = frozenset(p for p in out.split("\0")
                                    if p and os.path.isfile(os.path.join(self.root, p)))
        return self._files

    def pages(self):
        return sorted(p for p in self.files if p.endswith(".html") and not is_generated(p))

    def stylesheets(self):
        """*.css files, minus those pages load with <script src>: some files from the
        old WordPress mirror are JavaScript despite their .css name."""
        scripts = {self.url_to_file(t) for page in self.pages() for ref in self.refs(page)
                   if ref.tag == "script" and (t := local_target(page, ref.url))}
        return sorted(p for p in self.files if p.endswith(".css")
                      and not is_generated(p) and p not in scripts)

    def refs(self, path):
        """URL references in a page or stylesheet (parsed once, shared by the checks)."""
        if path not in self._refs:
            text = self.read(path)
            self._refs[path] = css_refs(text) if path.endswith(".css") else html_refs(text)
        return self._refs[path]

    def read(self, path):
        with open(os.path.join(self.root, path), "rb") as f:
            return f.read().decode("utf-8", "replace")

    def read_at_base(self, path):
        """Content of path at the merge-base, or None if it did not exist there."""
        try:
            return self.git("show", f"{self.merge_base}:{path}")
        except SiteError:
            return None

    def url_to_file(self, url_path):
        """The repository file the web server would serve for a URL path, or None."""
        rel = url_path.lstrip("/")
        candidates = [rel + "index.html"] if rel == "" or rel.endswith("/") else [rel, rel + "/index.html"]
        return next((c for c in candidates if c in self.files), None)

    # -- changes since the base ------------------------------------------------
    def changed_files(self, diff_filter):
        """Paths changed since the merge-base, e.g. diff_filter="M" for modified only."""
        out = self.git("diff", "--name-only", "-z", f"--diff-filter={diff_filter}",
                       "--find-renames", self.merge_base, "--")
        return sorted(p for p in out.split("\0") if p)

    def changed_lines(self):
        """Yield (path, line_number, text) for every added or modified line.

        Untracked (not ignored) files count as entirely new, so a local run
        before `git add` sees them too.
        """
        out = self.git("diff", "--unified=0", "--no-color", "--no-ext-diff",
                       "--find-renames", self.merge_base, "--")
        yield from _added_lines(out)
        untracked = self.git("ls-files", "-z", "--others", "--exclude-standard")
        for path in sorted(p for p in untracked.split("\0") if p):
            full = os.path.join(self.root, path)
            if not os.path.isfile(full):
                continue
            with open(full, "rb") as f:
                data = f.read()
            if b"\0" in data:
                continue  # binary
            for n, text in enumerate(data.decode("utf-8", "replace").split("\n"), 1):
                yield path, n, text


_HUNK_RE = re.compile(r"@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _added_lines(diff):
    """Parse `git diff --unified=0` output into (path, line_number, text)."""
    path, line_no, old_left, new_left = None, 0, 0, 0
    for raw in diff.split("\n"):
        if old_left or new_left:  # inside a hunk: count lines so content is never taken for a header
            if raw.startswith("+"):
                if path:
                    yield path, line_no, raw[1:]
                line_no += 1
                new_left -= 1
            elif raw.startswith("-"):
                old_left -= 1
            continue
        if raw.startswith("+++ "):
            target = raw[4:].strip('"')
            path = target[2:] if target.startswith("b/") else None  # None: deleted file
        elif raw.startswith("@@"):
            m = _HUNK_RE.match(raw)
            if m:
                old_left = int(m.group(1) if m.group(1) is not None else 1)
                line_no = int(m.group(2))
                new_left = int(m.group(3) if m.group(3) is not None else 1)
