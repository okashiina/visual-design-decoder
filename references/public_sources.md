# Public Sources

This skill uses public online sources only.

## Font references

- Google Fonts metadata:
  - `https://fonts.google.com/metadata/fonts`
- Fontsource public catalog:
  - `https://api.fontsource.org/v1/fonts`
- Public specimen URLs:
  - `https://fonts.google.com/specimen/<Family+Name>`

The analyzer uses style descriptors plus the local font profile list to produce likely matches, then verifies availability against public Google Fonts metadata and Fontsource when possible.

## Color references

- Color name dataset:
  - `https://unpkg.com/color-name-list/dist/colornames.json`

The analyzer uses nearest-color matching to enrich palette tokens with human-readable names.

## Failure behavior

If online lookup fails:
- keep local palette extraction
- keep local layout analysis
- keep font suggestions from local descriptor matching
- note the failure in `confidenceNotes`
