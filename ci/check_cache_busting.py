"""Cache-busting reminder: a changed shared asset under _static/ gets a new ?v=.

Browsers cache /_static/ files by their full URL. When an asset's content
changes, every page reference to it must use a ?v= value that no page used
before the change, or visitors keep the old copy. Only references in HTML
pages (outside messages/) are checked.
"""

from sitecheck import Finding, html_refs, is_generated, local_target, query_param

NAME = "cache-busting"
SUMMARY = "changed _static/ assets have their ?v= bumped wherever they are used"

STATIC_PREFIX = "_static/"


def versions_used(site, asset, pages, read):
    """{page: [(line, v or None)]} for references to asset in the given pages."""
    found = {}
    for page in pages:
        text = read(page)
        if text is None or asset.rsplit("/", 1)[-1] not in text:
            continue
        for ref in html_refs(text):
            target = local_target(page, ref.url)
            if target is not None and site.url_to_file(target) == asset:
                found.setdefault(page, []).append((ref.line, query_param(ref.url, "v")))
    return found


def run(site):
    changed = [p for p in site.changed_files(diff_filter="M") if p.startswith(STATIC_PREFIX)]
    if not changed:
        return []
    base_pages = [p for p in site.git("ls-tree", "-r", "-z", "--name-only", site.merge_base).split("\0")
                  if p.endswith(".html") and not is_generated(p)]
    findings = []
    for asset in changed:
        before = versions_used(site, asset, base_pages, site.read_at_base)
        old = {v for refs in before.values() for _, v in refs}
        now = versions_used(site, asset, site.pages(), site.read)
        for page, refs in sorted(now.items()):
            for line, v in refs:
                if v is None:
                    findings.append(Finding(page, line, f"{asset} changed: add ?v=N to this reference "
                                                        "so browsers fetch the new version"))
                elif v in old:
                    findings.append(Finding(page, line, f"{asset} changed: bump ?v={v} on this reference "
                                                        "(that version was already in use)"))
    return findings
