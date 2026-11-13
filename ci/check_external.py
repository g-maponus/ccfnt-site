"""No outside requests: pages and stylesheets load nothing from other hosts.

Scripts, stylesheets, fonts, images, iframes, media and <link rel="preconnect"/
"icon"/...> must come from ccfnt.org itself. Plain links (<a href>) to other sites
are fine. Exceptions live in ci/allowlist-external.txt, one per line:

    <repository path>  <host>   # why
"""

import os

from sitecheck import Finding, SITE_HOSTS, external_host

NAME = "external-requests"
SUMMARY = "pages load nothing from outside hosts (except ci/allowlist-external.txt)"

ALLOWLIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "allowlist-external.txt")


def load_allowlist(path=ALLOWLIST):
    allowed = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            fields = line.split("#", 1)[0].split()
            if len(fields) == 2:
                allowed.add((fields[0], fields[1].lower()))
            elif fields:
                raise ValueError(f"{path}: expected '<path> <host>', got: {line.strip()}")
    return allowed


def run(site):
    allowed = load_allowlist()
    findings = []
    for path in site.pages() + site.stylesheets():
        for ref in site.refs(path):
            if not ref.loads:
                continue
            host = external_host(ref.url)
            if host is None or host in SITE_HOSTS or (path, host) in allowed:
                continue
            findings.append(Finding(path, ref.line,
                                    f"{ref.where} loads from outside host '{host or '?'}' "
                                    "(self-host it, or add it to ci/allowlist-external.txt "
                                    "with G's approval)"))
    return findings
