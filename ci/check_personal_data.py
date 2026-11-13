"""Personal data and secrets, in changed lines only.

Flags email addresses and phone numbers (North American and French formats),
except public role contacts listed in ci/allowlist-contacts.txt, example
domains and fictional 555 numbers, and common token/key patterns. Reports file:line and the kind of match only:
the matched value is never printed, so the CI log does not republish it.
"""

import html
import os
import re
import urllib.parse

from sitecheck import Finding, is_generated

NAME = "personal-data"
SUMMARY = "changed lines contain no email addresses, phone numbers or secrets"

ALLOWLIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "allowlist-contacts.txt")

EMAIL_RE = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})")
# Reserved for documentation (RFC 2606 / RFC 6761, and the French "exemple"); never a real person.
EXAMPLE_DOMAINS_RE = re.compile(r"(^|\.)(ex[ae]mple\.(com|org|net|fr)|example|invalid|test|localhost)$", re.I)
ESCAPE_RE = re.compile(r"\\[nrt]")
# "logo@2x.png" looks like an address but is a file name.
FILE_SUFFIX_RE = re.compile(r"\.(png|jpe?g|gif|svg|webp|avif|ico|css|js|html?|pdf)$", re.I)

# (North American?, pattern). North American 555 numbers are fictional (form placeholders).
PHONE_PATTERNS = [
    # North America, with separators: (NXX) NXX-XXXX, NXX-NXX-XXXX, +1 NXX.NXX.XXXX
    (True, re.compile(r"(?<![\d.])(?:\+?1[\s.-]?)?(?:\([2-9]\d{2}\)\s?|[2-9]\d{2}[\s.-])[2-9]\d{2}[\s.-]\d{4}(?!\d)")),
    # E.164 North America: +1NXXNXXXXXX
    (True, re.compile(r"(?<!\d)\+1[2-9]\d{2}[2-9]\d{6}(?!\d)")),
    # France, national format with separators: 0X XX XX XX XX, 0X.XX.XX.XX.XX
    (False, re.compile(r"(?<![\d.])0[1-9](?:[\s.-]\d{2}){4}(?!\d)")),
    # France, international: +33 X XX XX XX XX, +33XXXXXXXXX, 0033 X...
    (False, re.compile(r"(?<!\d)(?:\+|00)33\s?\(?0?\)?\s?[1-9](?:[\s.-]?\d{2}){4}(?!\d)")),
    # tel:/sms: links with at least 7 digits
    (False, re.compile(r"(?:tel|sms):[+\d][\d\s().-]{6,}", re.I)),
]

TOKEN_PATTERNS = [
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("API key (sk-...)", re.compile(r"\bsk-[A-Za-z0-9_-]{24,}")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("Stripe key", re.compile(r"\b[rs]k_live_[0-9A-Za-z]{20,}")),
    ("private key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")),
    ("encoded token (JWT or tunnel token)", re.compile(r"\beyJ[A-Za-z0-9_+/=.-]{60,}")),
    ("password in a URL", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/:@'\"<>]+:[^\s/@'\"<>]+@", re.I)),
    ("hard-coded secret", re.compile(
        r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)"
        r"\b['\"]?\s*[:=]\s*['\"][^'\"\s]{8,}['\"]")),
]


def phone_key(text):
    """Last 9 digits, so a number matches with or without its +1/+33/0 prefix."""
    return re.sub(r"\D", "", text)[-9:]


def load_allowlist(path=ALLOWLIST):
    """(emails, phone keys) from the allowlist: entries with an @ are emails."""
    emails, phones = set(), set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            entry = line.split("#", 1)[0].strip()
            if "@" in entry:
                emails.add(entry.lower())
            elif entry:
                phones.add(phone_key(entry))
    return emails, phones


def is_listed_phone(number, north_american, allowed_phones):
    digits = re.sub(r"\D", "", number)
    return phone_key(digits) in allowed_phones or (north_american and digits[-7:-4] == "555")


def scan_line(text, allowlist):
    """Kinds of personal data or secrets found in one line (no values)."""
    allowed_emails, allowed_phones = allowlist
    text = ESCAPE_RE.sub(" ", text)  # "...\ncontact@..." in a JS/Python string
    variants = {text, html.unescape(urllib.parse.unquote(text))}  # catches %40 and &#64;
    kinds = []
    for variant in variants:
        for m in EMAIL_RE.finditer(variant):
            domain = m.group(1)
            if (m.group(0).lower() in allowed_emails or EXAMPLE_DOMAINS_RE.search(domain)
                    or FILE_SUFFIX_RE.search(domain)):
                continue
            kinds.append("email address")
        if any(not is_listed_phone(m.group(0), north_american, allowed_phones)
               for north_american, pattern in PHONE_PATTERNS for m in pattern.finditer(variant)):
            kinds.append("phone number")
        kinds += [kind for kind, pattern in TOKEN_PATTERNS if pattern.search(variant)]
    return sorted(set(kinds))


def run(site):
    allowed = load_allowlist()
    allowlist_path = os.path.relpath(ALLOWLIST, site.root).replace(os.sep, "/")
    findings = []
    for path, line, text in site.changed_lines():
        if is_generated(path) or path == allowlist_path:
            continue
        for kind in scan_line(text, allowed):
            findings.append(Finding(path, line, f"possible {kind} (value not shown; "
                                                "remove it, or ask G to allowlist a public role contact)"))
    return findings
