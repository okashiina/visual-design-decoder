# Visual Design Decoder

Turn a poster, banner, UI screenshot, packaging mockup, or menu image into practical design tokens for the web.

This repository contains an installable Codex skill and its local analysis script. It is built for the moment when you have a strong visual reference, but you need something more actionable than "make it look like this".

## What it does

`visual-design-decoder` helps translate an image into:

- likely hex colors
- typography direction and font guesses
- visual hierarchy observations
- reusable UI tokens for implementation
- web-friendly font replacement suggestions

## Why this exists

A lot of design inspiration starts as an image:

- a food poster with great typography
- a social graphic with a memorable palette
- a product card screenshot with nice spacing
- a packaging label with a strong visual mood

The hard part is translating that image into something a web UI can actually use.

This tool helps bridge that gap by producing:

1. a human-readable Markdown audit
2. a machine-friendly JSON token bundle

## What it analyzes

For a given image, the decoder tries to extract and infer:

- dominant, accent, and neutral colors
- likely background and contrast-heavy tones
- typography personality
- approximate font candidates
- likely web-safe replacements
- broad layout and composition signals
- component clues you can reuse in UI design

## How it works

The workflow is hybrid by design:

### 1. Local-first analysis

The script performs:

- palette extraction
- rough color grouping
- simple composition heuristics
- style-based font matching against curated font profiles

### 2. Web-assisted refinement

When internet access is available, it improves recommendations using public references such as:

- Google Fonts metadata
- Fontsource public catalog
- public color name references

If web lookups fail, it still returns useful local-only output.

## Example use cases

- "What are the main hex colors in this poster?"
- "Can you guess the fonts used here and suggest web alternatives?"
- "Extract design tokens from this image so I can rebuild it in React."
- "Analyze this menu/poster and tell me what makes the design feel warm or playful."

## Output

The analyzer can produce both:

### Markdown audit

Great for:

- design review
- redesign planning
- visual notes for a teammate
- quick creative direction handoff

### JSON token bundle

Great for:

- CSS variables
- design system prototyping
- UI implementation
- storing repeatable design analysis output

## Install as a skill

After publishing this repository:

```bash
npx skills add okashiina/visual-design-decoder@visual-design-decoder -g -y
```

The installable skill lives in:

- `visual-design-decoder/`

That nested structure is intentional so Codex skill installers can discover the skill by path.

## Local usage

Run the analyzer from the repository root:

```bash
python visual-design-decoder/scripts/analyze_image_design.py "C:\path\to\image.png" ^
  --headline-style "heavy rounded display headline" ^
  --supporting-style "playful handwritten supporting text"
```

Write structured output files:

```bash
python visual-design-decoder/scripts/analyze_image_design.py "C:\path\to\image.png" ^
  --json-out analysis.json ^
  --markdown-out analysis.md
```

Disable public web lookup:

```bash
python visual-design-decoder/scripts/analyze_image_design.py "C:\path\to\image.png" --no-web
```

## Repository structure

- `visual-design-decoder/SKILL.md`
- `visual-design-decoder/agents/openai.yaml`
- `visual-design-decoder/scripts/analyze_image_design.py`
- `visual-design-decoder/references/font_profiles.json`
- `visual-design-decoder/references/public_sources.md`
- `visual-design-decoder/examples/`

## Accuracy notes

This project is intentionally honest about what it can and cannot do.

It is good at:

- pulling usable palette values
- surfacing design direction
- suggesting likely font matches
- generating web-ready starting tokens

It is not meant to guarantee:

- exact font identification
- full OCR reconstruction
- pixel-perfect design reverse engineering

Think of it as a strong creative decoder, not a forensic design scanner.

## Public sources

By default, the project may use public online references such as:

- Google Fonts metadata
- Fontsource public catalog
- public color naming datasets

No paid API is required for v1.

## Requirements

- Python 3.10+
- `Pillow`
- `requests`

Install dependencies:

```bash
pip install -r visual-design-decoder/requirements.txt
```

## Future directions

Potential upgrades for later versions:

- stronger text region analysis
- attachment-first workflow helpers
- richer component segmentation
- optional OCR integration
- better font confidence scoring

## License

Add the license you want before publishing publicly.
