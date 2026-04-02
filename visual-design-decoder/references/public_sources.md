# Public Sources

This skill uses public online sources by default and can optionally accept a Canva font export for better matching.

## Font references

- Google Fonts metadata:
  - `https://fonts.google.com/metadata/fonts`
- Fontsource public catalog:
  - `https://api.fontsource.org/v1/fonts`
- Public specimen URLs:
  - `https://fonts.google.com/specimen/<Family+Name>`

The analyzer uses descriptor matching plus lightweight glyph-shape hints from the image itself to produce likely matches, then verifies availability against public catalogs when possible.

## Optional Canva adapter

Canva is not required.

If a user has access to a Canva app or their own Canva tooling, they can optionally provide a JSON export of the official `findFonts()` response.

Official Canva docs:
- `https://www.canva.dev/docs/apps/api/latest/asset-find-fonts/`

Important limitation from Canva's docs:
- `findFonts()` returns only a subset of Canva fonts.

The analyzer can use that export as an optional ranking signal through:
- `--canva-fonts-json path/to/canva-fonts.json`
- or `CANVA_FONTS_JSON=...`

Without it, the skill still works normally.

## Color references

- Color name dataset:
  - `https://unpkg.com/color-name-list/dist/colornames.json`

The analyzer uses nearest-color matching to enrich palette tokens with human-readable names.

## Failure behavior

If online lookup fails:
- keep local palette extraction
- keep local layout analysis
- keep font suggestions from local descriptor and glyph-hint matching
- note the failure in `confidenceNotes`
