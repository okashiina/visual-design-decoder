#!/usr/bin/env python3
"""
Analyze a design image and output reusable UI redesign tokens.

Usage:
  python scripts/analyze_image_design.py image.png
  python scripts/analyze_image_design.py image.png --headline-style "heavy rounded display"
  python scripts/analyze_image_design.py image.png --json-out tokens.json --markdown-out audit.md
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageFilter, ImageStat

ROOT = Path(__file__).resolve().parent.parent
FONT_PROFILES_PATH = ROOT / "references" / "font_profiles.json"
GOOGLE_FONTS_METADATA_URL = "https://fonts.google.com/metadata/fonts"
FONTSOURCE_CATALOG_URL = "https://api.fontsource.org/v1/fonts"
COLOR_NAMES_URL = "https://unpkg.com/color-name-list/dist/colornames.json"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hsl(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = [channel / 255 for channel in rgb]
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    l = (max_c + min_c) / 2

    if max_c == min_c:
        return 0.0, 0.0, l

    delta = max_c - min_c
    s = delta / (2 - max_c - min_c) if l > 0.5 else delta / (max_c + min_c)

    if max_c == r:
        h = ((g - b) / delta + (6 if g < b else 0)) / 6
    elif max_c == g:
        h = ((b - r) / delta + 2) / 6
    else:
        h = ((r - g) / delta + 4) / 6

    return h, s, l


def color_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


def dedupe_similar_colors(colors: list[dict[str, Any]], threshold: float = 24) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    for item in colors:
        if not any(color_distance(item["rgb"], existing["rgb"]) < threshold for existing in unique):
            unique.append(item)
    return unique


def load_image(path: Path) -> Image.Image:
    image = Image.open(path)
    return image.convert("RGB")


def extract_palette(image: Image.Image, max_colors: int = 12) -> list[dict[str, Any]]:
    thumb = image.copy()
    thumb.thumbnail((280, 280))
    quantized = thumb.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette() or []
    counts = quantized.getcolors() or []

    colors: list[dict[str, Any]] = []
    total = sum(count for count, _ in counts) or 1

    for count, palette_index in sorted(counts, reverse=True):
        rgb = tuple(palette[palette_index * 3 : palette_index * 3 + 3])  # type: ignore[assignment]
        h, s, l = rgb_to_hsl(rgb)
        colors.append(
            {
                "hex": rgb_to_hex(rgb),
                "rgb": rgb,
                "share": round(count / total, 4),
                "hsl": {"h": round(h, 4), "s": round(s, 4), "l": round(l, 4)},
            }
        )

    return dedupe_similar_colors(colors)


def classify_palette(colors: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    neutrals: list[dict[str, Any]] = []
    accents: list[dict[str, Any]] = []
    dominant: list[dict[str, Any]] = []

    for color in colors:
        saturation = color["hsl"]["s"]
        lightness = color["hsl"]["l"]

        if saturation < 0.16 or (lightness > 0.9 and saturation < 0.25):
            neutrals.append(color)
        elif saturation > 0.45 and 0.12 < lightness < 0.9:
            accents.append(color)
        else:
            dominant.append(color)

    if not dominant and colors:
        dominant = colors[:3]
    if not neutrals:
        neutrals = [color for color in colors if color not in accents][:3]
    if not accents:
        accents = [color for color in colors if color not in neutrals][:3]

    return {
        "dominant": dominant[:4],
        "accent": accents[:4],
        "neutral": neutrals[:4],
    }


def edge_background_color(image: Image.Image) -> str:
    width, height = image.size
    edge_pixels = []
    for x in range(width):
        edge_pixels.append(image.getpixel((x, 0)))
        edge_pixels.append(image.getpixel((x, height - 1)))
    for y in range(height):
        edge_pixels.append(image.getpixel((0, y)))
        edge_pixels.append(image.getpixel((width - 1, y)))

    dominant_rgb = Counter(edge_pixels).most_common(1)[0][0]
    return rgb_to_hex(dominant_rgb)


def band_summary(image: Image.Image) -> list[dict[str, Any]]:
    width, height = image.size
    bands: list[dict[str, Any]] = []
    gray = image.convert("L")
    edge_map = gray.filter(ImageFilter.FIND_EDGES)

    labels = ["top", "middle", "bottom"]
    for index, label in enumerate(labels):
        top = int(index * height / 3)
        bottom = int((index + 1) * height / 3)
        band = image.crop((0, top, width, bottom))
        band_edges = edge_map.crop((0, top, width, bottom))
        band_palette = extract_palette(band, max_colors=5)
        brightness = ImageStat.Stat(band.convert("L")).mean[0]
        edge_intensity = ImageStat.Stat(band_edges).mean[0]
        bands.append(
            {
                "label": label,
                "dominantHex": band_palette[0]["hex"] if band_palette else "#000000",
                "brightness": round(brightness, 2),
                "edgeDensity": round(edge_intensity / 255, 4),
            }
        )
    return bands


def infer_layout(bands: list[dict[str, Any]], background_hex: str) -> dict[str, Any]:
    densest = max(bands, key=lambda item: item["edgeDensity"])
    calmest = min(bands, key=lambda item: item["edgeDensity"])
    edge_profile = [band["edgeDensity"] for band in bands]

    if edge_profile[0] > edge_profile[1] and edge_profile[2] > edge_profile[1]:
        composition = "photo-led framing with a calmer central text band"
    elif edge_profile[1] > edge_profile[0] and edge_profile[1] > edge_profile[2]:
        composition = "type-led center with supporting visual material around it"
    else:
        composition = "balanced composition with text and imagery distributed across the canvas"

    spacing_feel = "airy and poster-like" if bands[1]["brightness"] > 200 else "compact with tighter visual stacking"

    image_regions = []
    for band in bands:
        if band["edgeDensity"] > 0.18:
            image_regions.append(f"{band['label']} band feels image-heavy")
        else:
            image_regions.append(f"{band['label']} band feels calmer and text-friendly")

    components = [
        {
            "name": "background field",
            "purpose": "main canvas tone",
            "visualTokens": [background_hex],
        },
        {
            "name": "headline block",
            "purpose": "primary title / offer callout",
            "visualTokens": [densest["dominantHex"]],
        },
        {
            "name": "supporting metadata line",
            "purpose": "contact, batch, or supporting details",
            "visualTokens": [calmest["dominantHex"]],
        },
    ]

    return {
        "composition": composition,
        "spacingFeel": spacing_feel,
        "imageRegions": image_regions,
        "components": components,
    }


def load_font_profiles() -> list[dict[str, Any]]:
    return json.loads(FONT_PROFILES_PATH.read_text(encoding="utf-8"))


def fetch_google_fonts_catalog(timeout: int = 10) -> set[str]:
    response = requests.get(GOOGLE_FONTS_METADATA_URL, timeout=timeout)
    response.raise_for_status()
    text = response.text
    if text.startswith(")]}'"):
        text = text.split("\n", 1)[1]
    payload = json.loads(text)
    return {font["family"] for font in payload.get("familyMetadataList", [])}


def fetch_fontsource_catalog(timeout: int = 10) -> set[str]:
    response = requests.get(FONTSOURCE_CATALOG_URL, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    return {font["family"] for font in payload}


def fetch_color_names(timeout: int = 10) -> list[dict[str, Any]]:
    response = requests.get(COLOR_NAMES_URL, timeout=timeout)
    response.raise_for_status()
    return response.json()


def nearest_color_name(hex_code: str, color_names: list[dict[str, Any]]) -> dict[str, Any] | None:
    target = hex_to_rgb(hex_code)
    best = None
    best_distance = float("inf")
    for entry in color_names:
        candidate = hex_to_rgb(entry["hex"])
        distance = color_distance(target, candidate)
        if distance < best_distance:
            best_distance = distance
            best = {"name": entry["name"], "hex": entry["hex"], "distance": round(distance, 2)}
    return best


def descriptor_keywords(value: str) -> set[str]:
    tokens = set()
    for chunk in value.lower().replace("/", " ").replace(",", " ").split():
        cleaned = chunk.strip()
        if cleaned:
            tokens.add(cleaned)
    return tokens


def score_font_profile(profile: dict[str, Any], desired_keywords: set[str]) -> int:
    tags = {tag.lower() for tag in profile.get("tags", [])}
    score = len(tags.intersection(desired_keywords)) * 3
    category = profile.get("category", "").lower()
    if category in desired_keywords:
        score += 2
    family = profile.get("family", "").lower()
    if any(keyword in family for keyword in desired_keywords):
        score += 1
    return score


def lookup_font_candidates(
    style_text: str,
    google_families: set[str] | None,
    fontsource_families: set[str] | None,
) -> list[dict[str, Any]]:
    profiles = load_font_profiles()
    keywords = descriptor_keywords(style_text)
    ranked = sorted(
        (
            {
                **profile,
                "score": score_font_profile(profile, keywords),
                "availableOnline": profile["family"] in google_families if google_families else None,
                "availableInFontsource": profile["family"] in fontsource_families if fontsource_families else None,
                "specimenUrl": f"https://fonts.google.com/specimen/{profile['family'].replace(' ', '+')}",
            }
            for profile in profiles
        ),
        key=lambda item: (
            item["score"],
            item.get("availableOnline") is True,
            item.get("availableInFontsource") is True,
        ),
        reverse=True,
    )
    results = [item for item in ranked if item["score"] > 0][:5]
    if results:
        return results

    fallback = [item for item in ranked if item.get("availableOnline") is not False][:5]
    return fallback


def choose_text_hex(palette: dict[str, list[dict[str, Any]]], background_hex: str) -> str:
    candidates = palette["accent"] + palette["dominant"] + palette["neutral"]
    background_rgb = hex_to_rgb(background_hex)
    best_hex = background_hex
    best_score = -1.0

    for item in candidates:
        rgb = hex_to_rgb(item["hex"])
        _, saturation, lightness = rgb_to_hsl(rgb)
        distance = color_distance(rgb, background_rgb)
        score = distance + saturation * 25 + (1 - lightness) * 35
        if score > best_score:
            best_score = score
            best_hex = item["hex"]

    return best_hex


def make_markdown(report: dict[str, Any]) -> str:
    palette = report["palette"]
    typography = report["typography"]
    layout = report["layout"]
    text_hex = choose_text_hex(
        {
            "dominant": palette["dominant"],
            "accent": palette["accent"],
            "neutral": palette["neutral"],
        },
        palette["background"],
    )
    lines = [
        "# Image Design Audit",
        "",
        "## Palette",
        f"- Background anchor: `{palette['background']}`",
        f"- Dominant: {', '.join(f'`{item['hex']}`' for item in palette['dominant']) or 'n/a'}",
        f"- Accent: {', '.join(f'`{item['hex']}`' for item in palette['accent']) or 'n/a'}",
        f"- Neutral: {', '.join(f'`{item['hex']}`' for item in palette['neutral']) or 'n/a'}",
        "",
        "## Typography",
        f"- Headline style guess: {typography['headline']['styleGuess']}",
        f"- Headline possible matches: {', '.join(item['family'] for item in typography['headline']['possibleMatches']) or 'n/a'}",
        f"- Headline web recommendations: {', '.join(typography['headline']['webRecommendations']) or 'n/a'}",
        f"- Supporting style guess: {typography['supporting']['styleGuess']}",
        f"- Supporting possible matches: {', '.join(item['family'] for item in typography['supporting']['possibleMatches']) or 'n/a'}",
        f"- Supporting web recommendations: {', '.join(typography['supporting']['webRecommendations']) or 'n/a'}",
        "",
        "## Layout",
        f"- Composition: {layout['composition']}",
        f"- Spacing feel: {layout['spacingFeel']}",
    ]
    lines.extend(f"- {region}" for region in layout["imageRegions"])
    lines.extend(
        [
            "",
            "## Components",
        ]
    )
    for component in report["components"]:
        lines.append(
            f"- **{component['name']}**: {component['purpose']} ({', '.join(component['visualTokens'])})"
        )

    lines.extend(
        [
            "",
            "## Suggested Tokens",
            "```css",
            ":root {",
            f"  --color-bg: {palette['background']};",
            f"  --color-text-strong: {text_hex};",
            f"  --color-accent: {palette['accent'][0]['hex'] if palette['accent'] else palette['background']};",
            f"  --font-display: \"{typography['headline']['webRecommendations'][0] if typography['headline']['webRecommendations'] else 'system-ui'}\", sans-serif;",
            f"  --font-supporting: \"{typography['supporting']['webRecommendations'][0] if typography['supporting']['webRecommendations'] else 'system-ui'}\", sans-serif;",
            "}",
            "```",
            "",
            "## Confidence Notes",
        ]
    )
    lines.extend(f"- {note}" for note in report["confidenceNotes"])
    return "\n".join(lines)


def build_report(
    image_path: Path,
    headline_style: str,
    supporting_style: str,
    no_web: bool,
) -> dict[str, Any]:
    image = load_image(image_path)
    colors = extract_palette(image)
    palette = classify_palette(colors)
    background = edge_background_color(image)
    bands = band_summary(image)
    layout = infer_layout(bands, background)
    confidence_notes = []
    sources_used = ["local-analysis"]

    google_families: set[str] | None = None
    fontsource_families: set[str] | None = None
    color_names: list[dict[str, Any]] | None = None

    if not no_web:
        try:
            google_families = fetch_google_fonts_catalog()
            sources_used.append("google-fonts")
        except Exception as exc:  # noqa: BLE001
            confidence_notes.append(f"Google Fonts lookup unavailable: {exc}")

        try:
            fontsource_families = fetch_fontsource_catalog()
            sources_used.append("public-font-catalog")
        except Exception as exc:  # noqa: BLE001
            confidence_notes.append(f"Public font catalog lookup unavailable: {exc}")

        try:
            color_names = fetch_color_names()
            sources_used.append("public-color-catalog")
        except Exception as exc:  # noqa: BLE001
            confidence_notes.append(f"Public color naming lookup unavailable: {exc}")

    if not headline_style:
        headline_style = "bold display headline"
        confidence_notes.append(
            "Headline style was not provided, so the analyzer used a generic bold-display fallback."
        )
    if not supporting_style:
        supporting_style = "friendly supporting text"
        confidence_notes.append(
            "Supporting style was not provided, so the analyzer used a generic friendly-supporting fallback."
        )

    headline_matches = lookup_font_candidates(
        headline_style,
        google_families,
        fontsource_families,
    )
    supporting_matches = lookup_font_candidates(
        supporting_style,
        google_families,
        fontsource_families,
    )

    def enrich_color_group(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enriched = []
        for item in items:
            enriched_item = {k: v for k, v in item.items() if k != "rgb"}
            if color_names:
                nearest = nearest_color_name(item["hex"], color_names)
                if nearest:
                    enriched_item["nearestPublicName"] = nearest["name"]
            enriched.append(enriched_item)
        return enriched

    report = {
        "input": {
            "path": str(image_path),
            "size": {"width": image.width, "height": image.height},
        },
        "palette": {
            "background": background,
            "dominant": enrich_color_group(palette["dominant"]),
            "accent": enrich_color_group(palette["accent"]),
            "neutral": enrich_color_group(palette["neutral"]),
        },
        "typography": {
            "headline": {
                "styleGuess": headline_style,
                "possibleMatches": headline_matches,
                "webRecommendations": [item["family"] for item in headline_matches[:3]],
                "confidence": "medium" if headline_matches else "low",
            },
            "supporting": {
                "styleGuess": supporting_style,
                "possibleMatches": supporting_matches,
                "webRecommendations": [item["family"] for item in supporting_matches[:3]],
                "confidence": "medium" if supporting_matches else "low",
            },
        },
        "layout": {
            "composition": layout["composition"],
            "spacingFeel": layout["spacingFeel"],
            "imageRegions": layout["imageRegions"],
            "bands": bands,
        },
        "components": layout["components"],
        "confidenceNotes": confidence_notes or [
            "Font suggestions are best-effort matches, not guaranteed original typefaces."
        ],
        "sourcesUsed": sources_used,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a design image into reusable UI tokens.")
    parser.add_argument("image_path", help="Path to the image file to analyze.")
    parser.add_argument("--headline-style", default="", help="Observed headline style descriptor.")
    parser.add_argument("--supporting-style", default="", help="Observed supporting text style descriptor.")
    parser.add_argument("--json-out", help="Optional path to write JSON output.")
    parser.add_argument("--markdown-out", help="Optional path to write Markdown audit output.")
    parser.add_argument("--no-web", action="store_true", help="Disable public web lookup and use local analysis only.")
    args = parser.parse_args()

    image_path = Path(args.image_path)
    if not image_path.exists():
        raise SystemExit(f"Image not found: {image_path}")

    report = build_report(
        image_path=image_path,
        headline_style=args.headline_style,
        supporting_style=args.supporting_style,
        no_web=args.no_web,
    )
    markdown = make_markdown(report)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.markdown_out:
        Path(args.markdown_out).write_text(markdown, encoding="utf-8")

    print(json.dumps({"report": report, "markdown": markdown}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
