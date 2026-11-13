"""HTML sanity: each page is UTF-8, parses, and has one <html lang> wrapping one
<head> and one <body>, with no nested <html>.
"""

import html.parser
import os

from sitecheck import Finding

NAME = "html-sanity"
SUMMARY = "pages parse, with one <html lang>, one <head>, one <body>"

STRUCTURE = ("html", "head", "body")


class _StructureParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.doctype = False
        self.opened = {tag: [] for tag in STRUCTURE}  # line numbers
        self.closed = {tag: 0 for tag in STRUCTURE}
        self.html_lang = None

    def handle_decl(self, decl):
        if decl.lower().startswith("doctype html"):
            self.doctype = True

    def handle_starttag(self, tag, attrs):
        if tag in STRUCTURE:
            self.opened[tag].append(self.getpos()[0])
            if tag == "html" and self.html_lang is None:
                self.html_lang = (dict(attrs).get("lang") or "").strip()

    def handle_endtag(self, tag):
        if tag in STRUCTURE:
            self.closed[tag] += 1


def check_page(path, raw):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        return [Finding(path, raw.count(b"\n", 0, e.start) + 1, "not valid UTF-8")]
    parser = _StructureParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as e:  # html.parser only raises on markup it cannot handle at all
        return [Finding(path, parser.getpos()[0], f"cannot be parsed: {e}")]

    findings = []
    if not parser.doctype:
        findings.append(Finding(path, 1, "missing <!DOCTYPE html>"))
    for tag in STRUCTURE:
        lines = parser.opened[tag]
        if not lines:
            findings.append(Finding(path, 0, f"no <{tag}> element"))
        elif len(lines) > 1:
            what = "nested <html>" if tag == "html" else f"more than one <{tag}>"
            findings.append(Finding(path, lines[1], what))
        elif parser.closed[tag] != 1:
            findings.append(Finding(path, lines[0], f"<{tag}> is closed {parser.closed[tag]} times "
                                                    "(expected once)"))
    if parser.opened["html"] and not parser.html_lang:
        findings.append(Finding(path, parser.opened["html"][0], "<html> has no lang attribute"))
    return findings


def run(site):
    findings = []
    for path in site.pages():
        with open(os.path.join(site.root, path), "rb") as f:
            findings += check_page(path, f.read())
    return findings
