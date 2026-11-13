"""Broken internal links and assets: every local href/src resolves to a file here.

Covers <a href>, <link href>, <script src>, <img src/srcset>, <iframe src>,
<form action>, CSS url()/@import, in pages and stylesheets. Skips other hosts,
/api/ (served by the API), /cdn-cgi/ (Cloudflare) and /messages/ (generated
on the server for now).
"""

from sitecheck import Finding, local_target

NAME = "internal-links"
SUMMARY = "every local href/src points to a file in the repository"


def run(site):
    findings = []
    for path in site.pages() + site.stylesheets():
        for ref in site.refs(path):
            target = local_target(path, ref.url)
            if target is None:
                continue
            if site.url_to_file(target) is None:
                findings.append(Finding(path, ref.line, f"{ref.where} points to {target}, "
                                                        "which is not a file in the repository"))
    return findings
