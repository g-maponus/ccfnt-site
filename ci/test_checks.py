"""Tests for the site checks: each check passes on a clean sample site and fails
on a deliberately broken one.

    python3 -m unittest discover -s ci -v

Personal-data samples are assembled at run time so that this file itself never
contains an address, a phone number or a token.
"""

import contextlib
import io
import os
import subprocess
import tempfile
import unittest

import check_cache_busting
import check_external
import check_html
import check_links
import check_personal_data
import run_checks
from sitecheck import Site, _added_lines

PAGE = """<!DOCTYPE html>
<html lang="fr">
<head>
<link rel="stylesheet" href="/_static/style.css?v=1">
<link rel="icon" href="/_static/logo.png">
</head>
<body>
<a href="page/">Page</a> <a href="https://www.usccb.org/">USCCB</a>
<a href="mailto:contact@ccfnt.org">contact@ccfnt.org</a>
<img src="../_static/logo.png" srcset="/_static/logo.png 1x, /_static/logo.png%3Fw=2 2x" alt="">
<form action="/api/subscribe"></form> <a href="/messages/">Messages</a>
<script src="/cdn-cgi/scripts/x.js"></script>
</body>
</html>
"""

FILES = {
    "index.html": PAGE,
    "page/index.html": PAGE.replace('href="page/"', 'href="../index.html#top"'),
    "_static/style.css": "body { background: url(logo.png); }\n",
    "_static/logo.png": "png",
    "_static/logo.png?w=2": "png",
    # Generated content is skipped by every check, however broken it is.
    "messages/m.html": "<html><html><img src='https://tracker.invalid/p.gif'><a href='/nope'>",
}

EMAIL = "jean.dupont" + "@" + "gmail.com"
PHONE_US = "(214) " + "200-" + "0000"
PHONE_FR = "06 12 " + "34 56 78"
TOKEN = "ghp_" + "A1b2C3d4" * 5


def git(root, *args):
    subprocess.run(["git", "-C", root, "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                   check=True, capture_output=True)


class SampleSite(unittest.TestCase):
    """A small committed site on branch `main`; tests edit it and run checks."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        git(self.root, "init", "-q", "-b", "main")
        for path, text in FILES.items():
            self.write(path, text)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "base")
        git(self.root, "switch", "-q", "-c", "work")

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, path, text):
        full = os.path.join(self.root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)

    def edit(self, path, old, new):
        with open(os.path.join(self.root, path), encoding="utf-8") as f:
            text = f.read()
        self.assertIn(old, text)
        self.write(path, text.replace(old, new))

    def findings(self, check):
        return check.run(Site(self.root, "main"))

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = run_checks.main(["--root", self.root, "--base", "main", *args])
        return status, out.getvalue()


class CleanSite(SampleSite):
    def test_all_checks_pass(self):
        status, out = self.cli()
        self.assertEqual(status, 0, out)
        self.assertIn("5 of 5 checks passed", out)

    def test_missing_base_is_an_error_not_a_pass(self):
        status, out = self.cli("--base", "no-such-branch")
        self.assertEqual(status, 2)
        self.assertIn("base 'no-such-branch' not found", out)


class ExternalRequests(SampleSite):
    def test_outside_script_fails(self):
        self.edit("index.html", "</head>", '<script src="https://cdn.example.net/x.js"></script>\n</head>')
        [f] = self.findings(check_external)
        self.assertEqual((f.path, f.line), ("index.html", 6))  # the <script> line
        self.assertIn("cdn.example.net", f.message)

    def test_outside_font_preconnect_iframe_and_css_fail(self):
        self.edit("index.html", "</head>", '<link rel="preconnect" href="//fonts.example.net">\n'
                                           '<style>@import "https://fonts.example.net/a.css";</style>\n</head>')
        self.edit("page/index.html", "<body>", '<body><iframe src="https://video.example.net/v"></iframe>')
        self.edit("_static/style.css", "url(logo.png)", "url(https://img.example.net/bg.png)")
        hosts = sorted(f.message.split("'")[1] for f in self.findings(check_external))
        self.assertEqual(hosts, ["fonts.example.net", "fonts.example.net", "img.example.net",
                                 "video.example.net"])

    def test_links_to_other_sites_and_allowlisted_embed_pass(self):
        self.write("messes/adresse/index.html",
                   PAGE.replace("<body>", '<body><iframe src="https://maps.google.com/maps?q=x"></iframe>'))
        self.assertEqual(self.findings(check_external), [])


class PersonalData(SampleSite):
    def test_email_phone_and_token_in_changed_lines_fail_without_printing_them(self):
        self.edit("index.html", "</body>", f"<p>{EMAIL}</p>\n<p>{PHONE_US} / {PHONE_FR}</p>\n"
                                           f"<script>const k = '{TOKEN}';</script>\n</body>")
        status, out = self.cli("--only", "personal-data")
        self.assertEqual(status, 1)
        self.assertIn("index.html:13: possible email address", out)
        self.assertIn("index.html:14: possible phone number", out)
        self.assertIn("index.html:15: possible GitHub token", out)
        for value in (EMAIL, PHONE_US, PHONE_FR, TOKEN, "jean", "200-", "A1b2"):
            self.assertNotIn(value, out)

    def test_obfuscated_email_and_new_untracked_file_fail(self):
        self.write("notes.txt", "contact " + EMAIL.replace("@", "&#64;") + "\n")
        [f] = self.findings(check_personal_data)
        self.assertEqual((f.path, f.line), ("notes.txt", 1))

    def test_allowed_addresses_and_unchanged_lines_pass(self):
        self.write("old.txt", EMAIL + "\n")
        git(self.root, "add", "old.txt")
        git(self.root, "commit", "-q", "-m", "already on main")
        git(self.root, "branch", "-f", "main")
        self.write("old.txt", EMAIL + "\ncontact@ccfnt.org, someone@example.org, logo@2x.png\n")
        self.assertEqual(self.findings(check_personal_data), [])

    def test_generated_messages_are_skipped(self):
        self.write("messages/new.html", f"<p>{EMAIL}</p>")
        self.assertEqual(self.findings(check_personal_data), [])


class ScanLine(unittest.TestCase):
    ALLOWLIST = ({"contact@ccfnt.org"}, {check_personal_data.phone_key("+1 972 " + "200 0001")})

    def scan(self, text):
        return check_personal_data.scan_line(text, self.ALLOWLIST)

    def test_allowed_contacts_placeholders_and_escapes_pass(self):
        self.assertEqual(self.scan('placeholder="(214) ' + '555-1234"'), [])  # fictional 555
        self.assertEqual(self.scan("Abbaye : (972) " + "200-0001"), [])     # allowlisted number
        self.assertEqual(self.scan('alert("Merci\\ncontact@ccfnt.org")'), [])
        self.assertEqual(self.scan("Prénom Nom\tprenom" + "@exemple.com"), [])

    def test_formats_are_flagged(self):
        for text in ("+33 6 12 " + "34 56 78", "+1214" + "2000000", 'href="tel:+33' + '612345678"',
                     "mailto:" + EMAIL.replace("@", "%40"), "password = '" + "hunter2hunter2'",
                     "https://user:" + "pass@host.example.net/"):
            self.assertNotEqual(self.scan(text), [], text)

    def test_numbers_that_are_not_phones_pass(self):
        for text in ("?m=1720530689i", "width:1000px; height:2000px", "0123456789abcdef", "v=10&w=240"):
            self.assertEqual(self.scan(text), [], text)


class InternalLinks(SampleSite):
    def test_missing_page_image_and_css_asset_fail(self):
        self.edit("index.html", "</body>", '<a href="/messes/nulle-part/">x</a>\n'
                                           '<img src="_static/missing.png" alt="">\n</body>')
        self.edit("_static/style.css", "url(logo.png)", "url(../img/bg.png)")
        found = sorted((f.path, f.line, f.message.split(" points to ")[1].split(",")[0])
                       for f in self.findings(check_links))
        self.assertEqual(found, [("_static/style.css", 1, "/img/bg.png"),
                                 ("index.html", 13, "/messes/nulle-part/"),
                                 ("index.html", 14, "/_static/missing.png")])

    def test_wrong_encoded_file_name_fails(self):
        self.edit("index.html", "logo.png%3Fw=2 2x", "logo.png%3Fw=3 2x")
        [f] = self.findings(check_links)
        self.assertIn("/_static/logo.png?w=3", f.message)

    def test_file_loaded_as_script_is_not_scanned_as_css(self):
        self.write("_static/likes.css", 'el.style.backgroundImage = "url(" + a + ")";\n')
        self.edit("index.html", "</body>", '<script src="/_static/likes.css"></script>\n</body>')
        self.assertEqual(self.findings(check_links), [])


class HtmlSanity(SampleSite):
    def test_nested_html_missing_lang_and_two_bodies_fail(self):
        self.edit("index.html", '<html lang="fr">', "<html>")
        self.edit("index.html", "<body>", "<body><html><body>")
        self.write("broken.html", "<p>no structure at all</p>")
        messages = sorted(f"{f.path}: {f.message}" for f in self.findings(check_html))
        self.assertEqual(messages, [
            "broken.html: missing <!DOCTYPE html>", "broken.html: no <body> element",
            "broken.html: no <head> element", "broken.html: no <html> element",
            "index.html: <html> has no lang attribute", "index.html: more than one <body>",
            "index.html: nested <html>",
        ])

    def test_invalid_utf8_fails(self):
        with open(os.path.join(self.root, "page/index.html"), "ab") as f:
            f.write(b"\xe9t\xe9\n")
        [f] = self.findings(check_html)
        self.assertIn("not valid UTF-8", f.message)


class CacheBusting(SampleSite):
    def test_changed_asset_without_new_version_fails(self):
        self.edit("_static/style.css", "body", "body, main")
        found = sorted((f.path, f.line) for f in self.findings(check_cache_busting))
        self.assertEqual(found, [("index.html", 4), ("page/index.html", 4)])

    def test_version_already_used_elsewhere_still_fails(self):
        self.edit("_static/style.css", "body", "body, main")
        self.edit("index.html", "style.css?v=1", "style.css?v=2")
        [f] = self.findings(check_cache_busting)
        self.assertEqual(f.path, "page/index.html")
        self.assertIn("bump ?v=1", f.message)

    def test_reference_without_version_fails(self):
        self.edit("_static/logo.png", "png", "png2")
        findings = self.findings(check_cache_busting)
        self.assertEqual(len(findings), 6)  # <link rel=icon>, <img src>, srcset 1x, on both pages
        self.assertTrue(all("add ?v=N" in f.message for f in findings))

    def test_bump_everywhere_passes(self):
        self.edit("_static/style.css", "body", "body, main")
        for page in ("index.html", "page/index.html"):
            self.edit(page, "style.css?v=1", "style.css?v=2")
        self.assertEqual(self.findings(check_cache_busting), [])


class DiffParser(unittest.TestCase):
    def test_added_line_that_looks_like_a_header_is_content(self):
        diff = ("diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1,0 +2,2 @@\n"
                "+++ looks like a header\n+@@ and a hunk\n"
                "diff --git a/y b/y\n--- a/y\n+++ /dev/null\n@@ -1 +0,0 @@\n-gone\n")
        self.assertEqual(list(_added_lines(diff)),
                         [("x", 2, "++ looks like a header"), ("x", 3, "@@ and a hunk")])


if __name__ == "__main__":
    unittest.main()
