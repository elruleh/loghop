# Social preview image checklist

The social preview (`docs/img/social-preview.png` and `.svg`) is what
shows up when loghop is shared on Twitter, LinkedIn, Slack, Discord,
Hacker News, etc.

## Current setup

- `docs/img/social-preview.png` (raster fallback)
- `docs/img/social-preview.svg` (vector source)

## Where to verify

After any change to social preview, verify by:

1. GitHub repo → Settings → Social preview
2. Check it loads and shows the project name + tagline clearly
3. https://www.opengraph.xyz/ — paste https://github.com/elruleh/loghop
4. Twitter card validator: https://cards-dev.twitter.com/validator

## Recommended dimensions

- 1280×640px (Twitter/LinkedIn optimal)
- < 1MB file size
- High contrast, readable at small sizes
- Project name visible without zooming
