# CLAUDE.md — ccfnt.org website

This repository is the public web root of **ccfnt.org**, the website of the Communauté Catholique
Francophone du Nord du Texas (CCFNT): a small bilingual (French/English) Catholic community in the
Dallas area. It is served as-is (static files, no build step). The owner is **@g-maponus** (G).

## How to work on a request

1. **Understand first.** Read the issue, the relevant pages and this file. For anything bigger than a
   small fix, reply on the issue with your plan (what, which files, risks) before changing code.
   If the request is ambiguous, ask one clear question instead of guessing.
2. **One issue → one branch → one PR.** Keep the change small and focused on the request. No drive-by
   rewrites, reformatting or unrelated clean-up.
3. **Verify your own work** and say exactly what you checked and what you could not check
   (e.g. real-browser rendering).
4. **PR description:** summary, linked issue (`Closes #N`), files changed, how you verified it,
   risk, rollback. In French or English, matching the issue.
5. **Never merge**, never push to `main`, never change anything under `.github/`. G reviews and merges.
   Merging does not deploy; deployment is handled outside this repository.

## Rules for this site

- **Public repository:** everything pushed is public immediately. **Never** commit secrets, tokens or
  **personal data** (members' names, email addresses, phone numbers, home addresses, children's
  names). The only email address to show publicly is `contact@ccfnt.org`. If you find personal data
  in the site, report it without quoting it.
- **French first**, English alongside where it exists; correct accents; warm, simple tone (a parish
  community, not a startup). No internal jargon on visitor-facing pages.
- **Plain HTML/CSS/vanilla JS.** No framework, build step, new dependency, external CDN/font,
  tracker, analytics or cookie unless G explicitly asks. Pages must stay fast on old phones.
- **Mobile and accessibility are part of "done":** works at 360 px, semantic HTML, alt text,
  sufficient contrast, keyboard usable. Dark mode exists (CSS variables on `:root` /
  `[data-theme="dark"]`) — keep both themes working.
- **CSS:** `_static/ccfnt-style-1.css` is a long shared stylesheet; scope new rules under a specific
  selector or media query (unscoped `!important` / `float` / `display` rules have broken the menu
  before). When you change a shared asset in `_static/`, **bump its `?v=N`** in every page that
  references it.
- **Never break URLs.** Page paths and links are shared in emails and SMS. If a path must change,
  add a redirect page and say so in the PR.
- **`messages/` is generated on the server** (message archive pages, `all-messages.json`,
  `index.json`, attachments). Do not edit it by hand; propose changes to how it is displayed instead.
- **`/api/...` endpoints are a fixed contract** (mass dates, SMS sign-up, RSVP, admin). The server
  code is not in this repository. Do not call write endpoints, submit forms, or design features that
  need a new endpoint without saying so explicitly in the plan.
- **`/admin/`** is protected server-side; never weaken it.
- `_static/ccfnt-next-mass.js` fills the "Prochaine Messe" box (`#milestone_widget-2-content`) from
  `/api/masses`; keep that element on content pages.
- **Never send messages** (email, SMS) and never add code that sends them.

## Checks before opening a PR

- No new requests to outside hosts (scripts, CSS, iframes, images, fonts). Allowed today: the Google
  Maps embed on `/messes/adresse/`.
- `git diff` reviewed for secrets and personal data.
- Internal links and asset paths you touched resolve to files in the repository.
- Pages you changed still parse as valid HTML and keep their structure (header, menu, sidebar, footer).
