# ccfnt.org — website

Static site of the **Communauté Catholique Francophone du Nord du Texas** (https://ccfnt.org).
This repository contains only the public web root; it is served as-is.

## Rules for contributions
- Work on a branch and open a pull request — `main` is protected.
- **Never commit secrets, tokens, or members' personal data** (emails, phone numbers,
  addresses). This repository is public; anything pushed is public immediately.
- No build step today: what is in this repository is what is published.

## Site checks (`ci/`)
Run them before opening a pull request (Python 3, nothing to install):

```sh
python3 ci/run_checks.py                  # compares your changes with origin/main
python3 ci/run_checks.py --base HEAD~1    # or with another branch/commit
python3 -m unittest discover -s ci        # tests of the checks themselves
```

The same command runs on every pull request as the `site-checks` job. Each problem is
reported as `file:line: message`; the command exits with 1 if any check fails.

| Check | What fails |
|---|---|
| `external-requests` | A page or stylesheet loads a script, CSS, font, image or iframe from another host. Allowed exceptions: `ci/allowlist-external.txt`. Plain links to other sites are fine. |
| `personal-data` | A **changed** line contains an email address, a phone number or something that looks like a token or key. Only the location is printed, never the value. Public role contacts (e.g. `contact@ccfnt.org`): `ci/allowlist-contacts.txt`. |
| `internal-links` | A local `href`/`src` (or CSS `url()`) points to a file that is not in the repository. `/api/`, `/messages/` and `/cdn-cgi/` are skipped. |
| `html-sanity` | A page is not UTF-8, has no `<!DOCTYPE html>`, no `<html lang>`, or more than one `<html>`, `<head>` or `<body>`. |
| `cache-busting` | A file in `_static/` changed, but a page still references it with an old (or no) `?v=`. |

`messages/` is generated on the server and is skipped by every check for now.
Adding a line to an allowlist needs G's approval in the pull request.
Untracked files are checked too; ignored files (`.gitignore`) are not.

© CCFNT. All rights reserved unless stated otherwise.
