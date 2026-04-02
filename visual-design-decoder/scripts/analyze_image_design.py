#!/usr/bin/env python3
"""
Analyze a design image and output reusable UI redesign tokens.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter
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
    lightness = (max_c + min_c) / 2
    if max_c == min_c:
        return 0.0, 0.0, lightness
    delta = max_c - min_c
    saturation = delta / (2 - max_c - min_c) if lightness > 0.5 else delta / (max_c + min_c)
    if max_c == r:
        hue = ((g - b) / delta + (6 if g < b else 0)) / 6
    elif max_c == g:
        hue = ((b - r) / delta + 2) / 6
    else:
        hue = ((r - g) / delta + 4) / 6
    return hue, saturation, lightness


def luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def color_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


def percentile(values: list[int], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(clamp(ratio, 0, 1) * (len(ordered) - 1))
    return float(ordered[index])


def dedupe_similar_colors(colors: list[dict[str, Any]], threshold: float = 24) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    for item in colors:
        if not any(color_distance(item["rgb"], existing["rgb"]) < threshold for existing in unique):
            unique.append(item)
    return unique


def load_image(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def resize_for_analysis(image: Image.Image, max_width: int = 900) -> Image.Image:
    if image.width <= max_width:
        return image.copy()
    ratio = max_width / image.width
    return image.resize((max_width, max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)


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
        hue, saturation, lightness = rgb_to_hsl(rgb)
        colors.append(
            {
                "hex": rgb_to_hex(rgb),
                "rgb": rgb,
                "share": round(count / total, 4),
                "hsl": {"h": round(hue, 4), "s": round(saturation, 4), "l": round(lightness, 4)},
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
    return {"dominant": dominant[:4], "accent": accents[:4], "neutral": neutrals[:4]}


def edge_background_color(image: Image.Image) -> str:
    width, height = image.size
    edge_pixels = []
    for x in range(width):
        edge_pixels.append(image.getpixel((x, 0)))
        edge_pixels.append(image.getpixel((x, height - 1)))
    for y in range(height):
        edge_pixels.append(image.getpixel((0, y)))
        edge_pixels.append(image.getpixel((width - 1, y)))
    return rgb_to_hex(Counter(edge_pixels).most_common(1)[0][0])


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
        bands.append(
            {
                "label": label,
                "dominantHex": band_palette[0]["hex"] if band_palette else "#000000",
                "brightness": round(ImageStat.Stat(band.convert("L")).mean[0], 2),
                "edgeDensity": round(ImageStat.Stat(band_edges).mean[0] / 255, 4),
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
    image_regions = [
        f"{band['label']} band feels image-heavy" if band["edgeDensity"] > 0.18 else f"{band['label']} band feels calmer and text-friendly"
        for band in bands
    ]
    return {
        "composition": composition,
        "spacingFeel": spacing_feel,
        "imageRegions": image_regions,
        "components": [
            {"name": "background field", "purpose": "main canvas tone", "visualTokens": [background_hex]},
            {"name": "headline block", "purpose": "primary title / offer callout", "visualTokens": [densest["dominantHex"]]},
            {"name": "supporting metadata line", "purpose": "contact, batch, or supporting details", "visualTokens": [calmest["dominantHex"]]},
        ],
    }


def load_font_profiles() -> list[dict[str, Any]]:
    return json.loads(FONT_PROFILES_PATH.read_text(encoding="utf-8-sig"))


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
        distance = color_distance(target, hex_to_rgb(entry["hex"]))
        if distance < best_distance:
            best_distance = distance
            best = {"name": entry["name"], "hex": entry["hex"], "distance": round(distance, 2)}
    return best


def descriptor_keywords(value: str) -> set[str]:
    lowered = value.lower()
    for needle in ["-", "/", ",", "(", ")", "[", "]"]:
        lowered = lowered.replace(needle, " ")
    return {chunk.strip() for chunk in lowered.split() if chunk.strip()}


def load_canva_font_catalog(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    source_path = Path(path)
    if not source_path.exists():
        return None
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    fonts = payload.get("fonts", payload) if isinstance(payload, dict) else payload
    if not isinstance(fonts, list):
        return None
    families = set()
    preview_urls: dict[str, str] = {}
    for item in fonts:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        clean_name = name.strip()
        families.add(clean_name)
        preview_url = item.get("previewUrl")
        if isinstance(preview_url, str) and preview_url:
            preview_urls[clean_name] = preview_url
    if not families:
        return None
    return {"families": families, "previewUrls": preview_urls}


def make_text_mask(image: Image.Image, background_hex: str) -> tuple[list[list[int]], Image.Image]:
    working = resize_for_analysis(image, max_width=960)
    grayscale = working.convert("L")
    pixels = list(grayscale.tobytes())
    bg_rgb = hex_to_rgb(background_hex)
    bg_luma = luminance(bg_rgb)
    high = percentile(pixels, 0.9)
    low = percentile(pixels, 0.1)
    choose_bright = abs(high - bg_luma) >= abs(low - bg_luma)
    width, height = working.size
    mask: list[list[int]] = [[0] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            rgb = working.getpixel((x, y))
            gray_value = grayscale.getpixel((x, y))
            distance = color_distance(rgb, bg_rgb)
            if choose_bright:
                keep = gray_value >= max(int(high * 0.88), int(bg_luma + 45)) and distance >= 38
            else:
                keep = gray_value <= min(int(low * 1.12), int(bg_luma - 45)) and distance >= 38
            mask[y][x] = 1 if keep else 0
    return mask, working


def connected_components(mask: list[list[int]]) -> list[list[tuple[int, int]]]:
    if not mask or not mask[0]:
        return []
    height = len(mask)
    width = len(mask[0])
    seen = [[False] * width for _ in range(height)]
    components: list[list[tuple[int, int]]] = []
    for y in range(height):
        for x in range(width):
            if not mask[y][x] or seen[y][x]:
                continue
            stack = [(x, y)]
            seen[y][x] = True
            points: list[tuple[int, int]] = []
            while stack:
                cx, cy = stack.pop()
                points.append((cx, cy))
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if 0 <= nx < width and 0 <= ny < height and mask[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            components.append(points)
    return components


def count_holes(component_mask: list[list[int]]) -> int:
    height = len(component_mask)
    width = len(component_mask[0]) if height else 0
    if not width:
        return 0
    seen = [[False] * width for _ in range(height)]
    holes = 0
    for y in range(height):
        for x in range(width):
            if component_mask[y][x] or seen[y][x]:
                continue
            stack = [(x, y)]
            seen[y][x] = True
            touches_edge = False
            while stack:
                cx, cy = stack.pop()
                if cx in (0, width - 1) or cy in (0, height - 1):
                    touches_edge = True
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if 0 <= nx < width and 0 <= ny < height and not component_mask[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if not touches_edge:
                holes += 1
    return holes


def component_metrics(points: list[tuple[int, int]]) -> dict[str, Any]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x + 1
    height = max_y - min_y + 1
    local_mask = [[0] * width for _ in range(height)]
    for x, y in points:
        local_mask[y - min_y][x - min_x] = 1
    row_cov = [sum(row) / max(1, width) for row in local_mask]
    col_cov = [sum(local_mask[row][col] for row in range(height)) / max(1, height) for col in range(width)]

    def band_peak(values: list[float], start_ratio: float, end_ratio: float) -> tuple[float, float]:
        start = int(clamp(start_ratio, 0, 1) * max(0, len(values) - 1))
        end = max(start + 1, int(clamp(end_ratio, 0, 1) * len(values)))
        band = values[start:end]
        if not band:
            return 0.0, 0.5
        peak = max(band)
        peak_index = start + band.index(peak)
        return peak, peak_index / max(1, len(values) - 1)

    top_peak, _ = band_peak(row_cov, 0.0, 0.28)
    middle_peak, middle_ratio = band_peak(row_cov, 0.28, 0.7)
    bottom_peak, _ = band_peak(row_cov, 0.68, 1.0)
    left_peak = max(col_cov[: max(1, width // 4)]) if width else 0.0
    right_peak = max(col_cov[-max(1, width // 4) :]) if width else 0.0
    corner_w = max(1, width // 5)
    corner_h = max(1, height // 5)
    corners = [
        [local_mask[row][col] for row in range(corner_h) for col in range(corner_w)],
        [local_mask[row][col] for row in range(corner_h) for col in range(width - corner_w, width)],
        [local_mask[row][col] for row in range(height - corner_h, height) for col in range(corner_w)],
        [local_mask[row][col] for row in range(height - corner_h, height) for col in range(width - corner_w, width)],
    ]
    corner_fill = sum(sum(corner) / max(1, len(corner)) for corner in corners) / len(corners)
    return {
        "bbox": [min_x, min_y, max_x, max_y],
        "width": width,
        "height": height,
        "area": len(points),
        "fillRatio": round(len(points) / max(1, width * height), 4),
        "aspectRatio": round(width / max(1, height), 4),
        "topBarPeak": round(top_peak, 4),
        "middleBarPeak": round(middle_peak, 4),
        "bottomBarPeak": round(bottom_peak, 4),
        "middleBarY": round(middle_ratio, 4),
        "leftStemPeak": round(left_peak, 4),
        "rightStemPeak": round(right_peak, 4),
        "cornerFill": round(corner_fill, 4),
        "holeCount": count_holes(local_mask),
    }


def select_headline_components(components: list[list[tuple[int, int]]], image_size: tuple[int, int]) -> list[dict[str, Any]]:
    width, height = image_size
    metrics = [component_metrics(points) for points in components]
    filtered = []
    for item in metrics:
        if item["area"] < max(70, (width * height) * 0.00012):
            continue
        if item["height"] < max(18, height * 0.06):
            continue
        if item["width"] < max(8, width * 0.006):
            continue
        filtered.append(item)
    if not filtered:
        return []
    filtered.sort(key=lambda item: item["area"], reverse=True)
    top = filtered[:18]
    max_height = max(item["height"] for item in top)
    return [item for item in top if item["height"] >= max_height * 0.55]


def infer_letterform_hints(image: Image.Image, background_hex: str) -> dict[str, Any]:
    width, height = image.size
    middle_crop = image.crop((int(width * 0.04), int(height * 0.25), int(width * 0.96), int(height * 0.62)))
    mask, working = make_text_mask(middle_crop, background_hex)
    components = connected_components(mask)
    headline_components = select_headline_components(components, working.size)
    if not headline_components:
        return {
            "headlineCropSize": {"width": working.width, "height": working.height},
            "detectedHints": [],
            "headlineGlyphs": 0,
            "eCandidateCount": 0,
            "averageMetrics": {},
            "notes": ["No reliable headline glyph components were isolated for letterform analysis."],
        }
    e_candidates = []
    for item in headline_components:
        if item["leftStemPeak"] >= 0.75 and item["topBarPeak"] >= 0.45 and item["middleBarPeak"] >= 0.25 and item["bottomBarPeak"] >= 0.45 and item["rightStemPeak"] <= 0.45 and item["holeCount"] == 0:
            e_candidates.append(item)
    avg_corner_fill = sum(item["cornerFill"] for item in headline_components) / len(headline_components)
    avg_fill = sum(item["fillRatio"] for item in headline_components) / len(headline_components)
    avg_aspect = sum(item["aspectRatio"] for item in headline_components) / len(headline_components)
    hints: list[str] = []
    notes: list[str] = []
    if avg_corner_fill < 0.17:
        hints.append("rounded-corners")
    if avg_fill > 0.48:
        hints.append("chunky")
    if avg_aspect < 0.68:
        hints.append("condensed")
    middle_bar_ratio = None
    if e_candidates:
        middle_bar_ratio = sum(item["middleBarY"] for item in e_candidates) / len(e_candidates)
        if middle_bar_ratio < 0.43:
            hints.append("midbar-high")
        elif middle_bar_ratio < 0.56:
            hints.append("midbar-center")
        else:
            hints.append("midbar-low")
        notes.append(f"Detected {len(e_candidates)} E-like glyph candidate(s); average middle-bar ratio is {middle_bar_ratio:.3f}.")
    else:
        notes.append("No strong E-like glyph candidates were detected, so middle-bar hints are unavailable.")
    return {
        "headlineCropSize": {"width": working.width, "height": working.height},
        "headlineGlyphs": len(headline_components),
        "eCandidateCount": len(e_candidates),
        "detectedHints": hints,
        "averageMetrics": {
            "cornerFill": round(avg_corner_fill, 4),
            "fillRatio": round(avg_fill, 4),
            "aspectRatio": round(avg_aspect, 4),
            "middleBarY": round(middle_bar_ratio, 4) if middle_bar_ratio is not None else None,
        },
        "notes": notes,
    }


def score_font_profile(profile: dict[str, Any], desired_keywords: set[str], letterform_hints: list[str] | None, canva_families: set[str] | None) -> int:
    tags = {tag.lower() for tag in profile.get("tags", [])}
    shape_hints = {tag.lower() for tag in profile.get("shapeHints", [])}
    score = len(tags.intersection(desired_keywords)) * 3
    category = profile.get("category", "").lower()
    if category in desired_keywords:
        score += 2
    family = profile.get("family", "").lower()
    if any(keyword in family for keyword in desired_keywords):
        score += 1
    if letterform_hints:
        score += len(shape_hints.intersection({hint.lower() for hint in letterform_hints})) * 4
    if canva_families and profile.get("family") in canva_families:
        score += 1
    return score


def lookup_font_candidates(style_text: str, google_families: set[str] | None, fontsource_families: set[str] | None, letterform_hints: list[str] | None = None, canva_families: set[str] | None = None, canva_preview_urls: dict[str, str] | None = None) -> list[dict[str, Any]]:
    profiles = load_font_profiles()
    keywords = descriptor_keywords(style_text)
    ranked = sorted(
        (
            {
                **profile,
                "score": score_font_profile(profile, keywords, letterform_hints, canva_families),
                "availableOnline": profile["family"] in google_families if google_families else None,
                "availableInFontsource": profile["family"] in fontsource_families if fontsource_families else None,
                "availableInCanva": profile["family"] in canva_families if canva_families else None,
                "specimenUrl": f"https://fonts.google.com/specimen/{profile['family'].replace(' ', '+')}",
                **({"canvaPreviewUrl": canva_preview_urls.get(profile["family"])} if canva_preview_urls and profile["family"] in canva_preview_urls else {}),
            }
            for profile in profiles
        ),
        key=lambda item: (item["score"], item.get("availableInCanva") is True, item.get("availableOnline") is True, item.get("availableInFontsource") is True),
        reverse=True,
    )
    results = [item for item in ranked if item["score"] > 0][:6]
    return results or [item for item in ranked if item.get("availableOnline") is not False][:6]


def choose_text_hex(palette: dict[str, list[dict[str, Any]]], background_hex: str) -> str:
    candidates = palette["accent"] + palette["dominant"] + palette["neutral"]
    background_rgb = hex_to_rgb(background_hex)
    best_hex = background_hex
    best_score = -1.0
    for item in candidates:
        rgb = hex_to_rgb(item["hex"])
        _, saturation, lightness = rgb_to_hsl(rgb)
        score = color_distance(rgb, background_rgb) + saturation * 25 + (1 - lightness) * 35
        if score > best_score:
            best_score = score
            best_hex = item["hex"]
    return best_hex


def make_markdown(report: dict[str, Any]) -> str:
    palette = report["palette"]
    typography = report["typography"]
    layout = report["layout"]
    letterforms = report["letterforms"]
    text_hex = choose_text_hex({"dominant": palette["dominant"], "accent": palette["accent"], "neutral": palette["neutral"]}, palette["background"])
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
        "## Letterform Hints",
        f"- Detected hints: {', '.join(letterforms['detectedHints']) if letterforms['detectedHints'] else 'n/a'}",
    ]
    lines.extend(f"- {note}" for note in letterforms["notes"])
    lines.extend(["", "## Layout", f"- Composition: {layout['composition']}", f"- Spacing feel: {layout['spacingFeel']}"])
    lines.extend(f"- {region}" for region in layout["imageRegions"])
    lines.extend(["", "## Components"])
    for component in report["components"]:
        lines.append(f"- **{component['name']}**: {component['purpose']} ({', '.join(component['visualTokens'])})")
    if report.get("canva", {}).get("connected"):
        lines.extend(["", "## Canva Adapter", "- Canva font subset was provided and used as an optional ranking signal.", "- Note: Canva's official `findFonts` endpoint only returns a subset of fonts."])
    else:
        lines.extend(["", "## Optional Canva Adapter", "- Not connected for this run.", "- Future users can optionally provide a Canva `findFonts()` JSON export to enrich font ranking."])
    lines.extend(["", "## Suggested Tokens", "```css", ":root {", f"  --color-bg: {palette['background']};", f"  --color-text-strong: {text_hex};", f"  --color-accent: {palette['accent'][0]['hex'] if palette['accent'] else palette['background']};", f"  --font-display: \"{typography['headline']['webRecommendations'][0] if typography['headline']['webRecommendations'] else 'system-ui'}\", sans-serif;", f"  --font-supporting: \"{typography['supporting']['webRecommendations'][0] if typography['supporting']['webRecommendations'] else 'system-ui'}\", sans-serif;", "}", "```", "", "## Confidence Notes"])
    lines.extend(f"- {note}" for note in report["confidenceNotes"])
    return "\n".join(lines)


def build_report(image_path: Path, headline_style: str, supporting_style: str, no_web: bool, canva_fonts_json: str | None) -> dict[str, Any]:
    image = load_image(image_path)
    colors = extract_palette(image)
    palette = classify_palette(colors)
    background = edge_background_color(image)
    bands = band_summary(image)
    layout = infer_layout(bands, background)
    letterforms = infer_letterform_hints(image, background)
    confidence_notes: list[str] = []
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
    canva_catalog = load_canva_font_catalog(canva_fonts_json or os.environ.get("CANVA_FONTS_JSON"))
    canva_families = canva_catalog["families"] if canva_catalog else None
    canva_preview_urls = canva_catalog["previewUrls"] if canva_catalog else None
    if canva_catalog:
        sources_used.append("canva-fonts")
    else:
        confidence_notes.append("Optional Canva adapter not connected. Future users can provide a Canva findFonts() JSON export to enrich font ranking.")
    if not headline_style:
        headline_style = "bold display headline"
        confidence_notes.append("Headline style was not provided, so the analyzer used a generic bold-display fallback.")
    if not supporting_style:
        supporting_style = "friendly supporting text"
        confidence_notes.append("Supporting style was not provided, so the analyzer used a generic friendly-supporting fallback.")
    headline_matches = lookup_font_candidates(headline_style, google_families, fontsource_families, letterforms["detectedHints"], canva_families, canva_preview_urls)
    supporting_matches = lookup_font_candidates(supporting_style, google_families, fontsource_families, None, canva_families, canva_preview_urls)

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

    if not any("best-effort" in note for note in confidence_notes):
        confidence_notes.append("Font suggestions are best-effort matches, not guaranteed original typefaces.")
    return {
        "input": {"path": str(image_path), "size": {"width": image.width, "height": image.height}},
        "palette": {"background": background, "dominant": enrich_color_group(palette["dominant"]), "accent": enrich_color_group(palette["accent"]), "neutral": enrich_color_group(palette["neutral"])},
        "typography": {
            "headline": {"styleGuess": headline_style, "possibleMatches": headline_matches, "webRecommendations": [item["family"] for item in headline_matches[:3]], "confidence": "medium" if headline_matches else "low"},
            "supporting": {"styleGuess": supporting_style, "possibleMatches": supporting_matches, "webRecommendations": [item["family"] for item in supporting_matches[:3]], "confidence": "medium" if supporting_matches else "low"},
        },
        "letterforms": letterforms,
        "layout": {"composition": layout["composition"], "spacingFeel": layout["spacingFeel"], "imageRegions": layout["imageRegions"], "bands": bands},
        "components": layout["components"],
        "canva": {
            "connected": bool(canva_catalog),
            "source": canva_fonts_json or os.environ.get("CANVA_FONTS_JSON"),
            "note": "Canva support is optional and based on a user-provided findFonts() JSON export. Canva's official API only returns a subset of fonts." if canva_catalog else "Not connected. Canva enrichment is optional.",
        },
        "confidenceNotes": confidence_notes,
        "sourcesUsed": sources_used,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a design image into reusable UI tokens.")
    parser.add_argument("image_path", help="Path to the image file to analyze.")
    parser.add_argument("--headline-style", default="", help="Observed headline style descriptor.")
    parser.add_argument("--supporting-style", default="", help="Observed supporting text style descriptor.")
    parser.add_argument("--json-out", help="Optional path to write JSON output.")
    parser.add_argument("--markdown-out", help="Optional path to write Markdown audit output.")
    parser.add_argument("--no-web", action="store_true", help="Disable public web lookup and use local analysis only.")
    parser.add_argument("--canva-fonts-json", help="Optional path to a Canva findFonts() JSON export.")
    args = parser.parse_args()
    image_path = Path(args.image_path)
    if not image_path.exists():
        raise SystemExit(f"Image not found: {image_path}")
    report = build_report(image_path, args.headline_style, args.supporting_style, args.no_web, args.canva_fonts_json)
    markdown = make_markdown(report)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.markdown_out:
        Path(args.markdown_out).write_text(markdown, encoding="utf-8")
    print(json.dumps({"report": report, "markdown": markdown}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
