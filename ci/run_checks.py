#!/usr/bin/env python3
"""Run the ccfnt.org site checks.

    python3 ci/run_checks.py                 # all checks, changes compared with origin/main
    python3 ci/run_checks.py --base HEAD~3   # compare with another commit
    python3 ci/run_checks.py --only internal-links,html-sanity

Exit status: 0 all checks pass, 1 a check found problems, 2 the checks could not run.
"""

import argparse
import os
import sys

import check_cache_busting
import check_external
import check_html
import check_links
import check_personal_data
from sitecheck import Site, SiteError

CHECKS = [check_external, check_personal_data, check_links, check_html, check_cache_busting]


def annotation(check, finding):
    """GitHub Actions error annotation, shown on the pull request's changed files."""
    def escape(value, prop=False):
        value = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        return value.replace(":", "%3A").replace(",", "%2C") if prop else value
    location = f"file={escape(finding.path, True)}"
    if finding.line:
        location += f",line={finding.line}"
    return f"::error {location},title={escape(check.NAME, True)}::{escape(finding.message)}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="origin/main",
                        help="branch or commit to compare changes with (default: origin/main)")
    parser.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        help="repository to check (default: this one)")
    parser.add_argument("--only", help="comma-separated check names: " + ", ".join(c.NAME for c in CHECKS))
    args = parser.parse_args(argv)

    checks = CHECKS
    if args.only:
        wanted = set(args.only.split(","))
        unknown = wanted - {c.NAME for c in CHECKS}
        if unknown:
            parser.error(f"unknown check(s): {', '.join(sorted(unknown))}")
        checks = [c for c in CHECKS if c.NAME in wanted]

    site = Site(args.root, args.base)
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    failed = 0
    for check in checks:
        try:
            findings = check.run(site)
        except (SiteError, OSError, ValueError) as e:
            print(f"ERROR {check.NAME}: {e}")
            if in_actions:
                print(f"::error title={check.NAME}::{e}")
            return 2
        if not findings:
            print(f"PASS  {check.NAME}: {check.SUMMARY}")
            continue
        failed += 1
        print(f"FAIL  {check.NAME}: {len(findings)} problem(s) — {check.SUMMARY}")
        for finding in findings:
            print(f"      {finding}")
            if in_actions:
                print(annotation(check, finding))
    print(f"\n{len(checks) - failed} of {len(checks)} checks passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
