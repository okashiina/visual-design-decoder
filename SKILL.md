---
name: image-design-token-extractor
description: Analyze a local design image or attached image to extract likely hex palette, font guesses, layout hierarchy, and reusable web UI tokens. Use when a user asks what colors/fonts a visual uses, wants design tokens from a poster or screenshot, or needs a redesign handoff from an image.
---

# Image Design Token Extractor

## Overview

Use this skill when a user wants to turn a visual artifact into practical redesign inputs. It is built for image-first analysis of posters, UI screenshots, banners, packaging, menus, and other visual references where the goal is to identify palette, typography direction, hierarchy, and reusable web tokens.

This skill supports:
- local image paths
- attached chat images already visible to the agent

It produces:
- a Markdown audit for humans
- a JSON token bundle for implementation

## Workflow

### 1. Inspect the image first

Always inspect the image visually before running any script.

Decide:
- what appears to be the **headline** text style
- what appears to be the **supporting** text style
- what the overall composition feels like
- whether the image is mostly:
  - photo-led
  - type-led
  - balanced

For attached images without a local filesystem path:
- do the visual inspection directly from the attachment
- if no local path exists, skip the script and produce a best-effort audit using visual inspection plus public web lookup ideas

### 2. Run the analyzer for local image paths

For local image files, run:

```bash
python scripts/analyze_image_design.py "PATH_TO_IMAGE" \
  --headline-style "heavy rounded display" \
  --supporting-style "playful handwritten supporting text"
```

Useful flags:

```bash
python scripts/analyze_image_design.py "PATH_TO_IMAGE" --no-web
python scripts/analyze_image_design.py "PATH_TO_IMAGE" --json-out tokens.json --markdown-out audit.md
```

What the script does:
- extracts dominant colors
- groups colors into dominant / accent / neutral
- estimates background and contrast-heavy regions
- infers rough composition from horizontal bands
- uses public web lookup to refine:
  - color naming
  - likely font replacement candidates

### 3. Interpret the output carefully

Treat the results in three buckets:

- **Observed facts**
  - hex palette candidates
  - dominant/neutral/accent balance
  - composition observations
- **Best-effort guesses**
  - style labels like "heavy rounded display" or "friendly handwritten"
  - font family candidates
- **Recommended replacements for web**
  - web-safe fonts
  - suggested CSS variables
  - implementation-friendly component mapping

Never present font matches as guaranteed. Always call them likely matches or recommended substitutes unless the image itself clearly embeds a known typeface.

### 4. Build the final answer

When reporting results, include:
- color palette with hex codes
- likely headline/supporting font direction
- possible font matches
- recommended web replacements
- layout and component notes
- CSS token suggestions

Use this structure:

```markdown
## Palette
- Dominant:
- Accent:
- Neutral:

## Typography
- Headline style guess:
- Supporting style guess:
- Possible matches:
- Web replacements:

## Layout
- Composition:
- Spacing feel:
- Visual hierarchy:

## Components
- Hero image/photo region:
- Headline block:
- Metadata/supporting line:

## Suggested Tokens
```css
:root {
  --bg: ...;
  --text: ...;
  --accent: ...;
}
```
```

## Public Web Lookup

This skill is allowed to use public online references to improve accuracy.

Default sources:
- Google Fonts metadata
- public font catalogs/directories
- public color naming references

If public web lookup fails:
- fall back to local-only analysis
- still produce the audit
- explicitly note that online refinement was unavailable

## References

- Font descriptor mapping and scoring logic: `references/font_profiles.json`
- Public-source notes and expected behavior: `references/public_sources.md`

## Output Expectations

The final JSON token bundle should contain, at minimum:
- `palette`
- `typography`
- `layout`
- `components`
- `confidenceNotes`
- `sourcesUsed`

The final Markdown audit should mirror the JSON but explain the results in human-friendly language and clearly separate observation from recommendation.
