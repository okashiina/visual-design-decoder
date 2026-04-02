# Image Design Token Extractor

Analyze a design image and turn it into practical UI redesign inputs:

- dominant hex palette
- likely font/style matches
- layout and component observations
- suggested CSS-ready design tokens

This repo is packaged as an installable Codex skill.

## What it does

The skill uses a hybrid workflow:

1. local image analysis for palette and composition
2. heuristic typography matching from curated font profiles
3. public web lookup for better font and color reference accuracy

It produces:

- a Markdown audit for humans
- a JSON token bundle for implementation

## Usage

```bash
python scripts/analyze_image_design.py "C:\path\to\image.png" ^
  --headline-style "heavy rounded display headline" ^
  --supporting-style "playful handwritten supporting text"
```

Optional output files:

```bash
python scripts/analyze_image_design.py "C:\path\to\image.png" ^
  --json-out analysis.json ^
  --markdown-out analysis.md
```

Disable public web lookup if needed:

```bash
python scripts/analyze_image_design.py "C:\path\to\image.png" --no-web
```

## Public sources used

- Google Fonts metadata
- Fontsource public catalog
- public color naming dataset

If those lookups fail, the analyzer still falls back to local-only output.

## Skill installation

After publishing this repo:

```bash
npx skills add <owner>/<repo>@image-design-token-extractor -g -y
```

## Repository structure

- `SKILL.md`: skill instructions
- `agents/openai.yaml`: skill metadata
- `scripts/analyze_image_design.py`: analyzer
- `references/`: font profiles and public source notes
- `examples/`: sample outputs
