---
name: sites
description: Create, update, list and share private web pages (HTML sites) for the person. Use when they ask for a page, report, dashboard, chart, comparison or anything easier to look at than read in chat, or ask what pages already exist.
---

# Private sites

You can host web pages for the person. Every folder in `sites/` (in your
workspace) is served at a private URL that only their own devices can open.
Use this when a page beats a chat message: tables, charts, comparisons,
reports, small interactive tools.

## See what already exists

```
python3 .claude/skills/sites/list_sites.py
```

This prints each site's name, URL, last update, title and description. Check
it first: if a fitting site exists, update it instead of making a new one.

## Create or update a site

1. Pick a short folder name: lowercase words joined by hyphens, like `laptop-comparison`.
2. Write `sites/<name>/index.html`. Extra files (CSS, JS, images, data) can sit next to it.
3. Always include `<title>`, `<meta name="description" content="one line about the page">`
   and `<meta name="viewport" content="width=device-width, initial-scale=1">`.
   The title and description are how you'll recognise the site later.
4. The person mostly opens these on a phone: make the page readable on a small screen.
5. Keep it self-contained. Inline CSS and JS are best; libraries from a CDN are fine.
6. Updating a site keeps the same URL, so the person's old link shows the new version.

## Share it

Run `list_sites.py` to get the site's URL and put that link in your final
message, with one line on what's on the page.

## Rules

- Pages are private to the person's devices, but never put passwords, API keys
  or tokens in a page.
- Don't delete a site unless the person asks.
