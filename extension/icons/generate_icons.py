#!/usr/bin/env python3
"""
Generate Bili Analyzer Chrome extension icons.
Icon concept: B站 blue play button triangle with a small document overlay.
"""

from PIL import Image, ImageDraw
import math

BILI_BLUE = (0, 161, 214)       # #00a1d6
DARK_BLUE = (0, 120, 170)
WHITE = (255, 255, 255)
DOC_BG = (255, 255, 255)
DOC_BORDER = (80, 80, 80)


def draw_rounded_rect(draw, bbox, radius, fill):
    """Draw a filled rounded rectangle."""
    x0, y0, x1, y1 = bbox
    r = radius
    draw.ellipse([x0, y0, x0 + 2*r, y0 + 2*r], fill=fill)
    draw.ellipse([x1 - 2*r, y0, x1, y0 + 2*r], fill=fill)
    draw.ellipse([x0, y1 - 2*r, x0 + 2*r, y1], fill=fill)
    draw.ellipse([x1 - 2*r, y1 - 2*r, x1, y1], fill=fill)
    draw.rectangle([x0 + r, y0, x1 - r, y1], fill=fill)
    draw.rectangle([x0, y0 + r, x1, y1 - r], fill=fill)


def generate_icon(size):
    """Generate a single icon at the given size."""
    # Work at 4x resolution for antialiasing, then downscale
    scale = 4
    s = size * scale
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = int(s * 0.06)
    radius = int(s * 0.18)

    # Background: rounded rectangle with bili blue
    draw_rounded_rect(draw, [margin, margin, s - margin, s - margin], radius, fill=BILI_BLUE)

    # Play triangle (white), centered slightly left to leave room for doc overlay
    cx = s * 0.44
    cy = s * 0.50
    tri_size = s * 0.30

    p1 = (cx - tri_size * 0.4, cy - tri_size * 0.55)
    p2 = (cx - tri_size * 0.4, cy + tri_size * 0.55)
    p3 = (cx + tri_size * 0.55, cy)
    draw.polygon([p1, p2, p3], fill=WHITE)

    # Small document/note overlay in the bottom-right corner
    doc_w = s * 0.30
    doc_h = s * 0.36
    doc_x = s * 0.62
    doc_y = s * 0.54

    # Shadow
    shadow_off = int(s * 0.015)
    draw.rectangle(
        [doc_x + shadow_off, doc_y + shadow_off,
         doc_x + doc_w + shadow_off, doc_y + doc_h + shadow_off],
        fill=(0, 0, 0, 60)
    )
    # Document rectangle
    draw.rectangle([doc_x, doc_y, doc_x + doc_w, doc_y + doc_h],
                   fill=DOC_BG, outline=DOC_BORDER, width=max(1, int(s * 0.012)))

    # Folded corner
    fold = s * 0.08
    fold_points = [
        (doc_x + doc_w - fold, doc_y),
        (doc_x + doc_w, doc_y + fold),
        (doc_x + doc_w, doc_y),
    ]
    draw.polygon(fold_points, fill=(220, 220, 220))
    draw.line(
        [(doc_x + doc_w - fold, doc_y),
         (doc_x + doc_w - fold, doc_y + fold),
         (doc_x + doc_w, doc_y + fold)],
        fill=DOC_BORDER, width=max(1, int(s * 0.01))
    )

    # Text lines on document
    line_color = (100, 100, 100)
    lw = max(1, int(s * 0.012))
    line_margin_x = s * 0.04
    line_spacing = s * 0.055
    line_start_y = doc_y + s * 0.10

    for i in range(3):
        ly = line_start_y + i * line_spacing
        lx_start = doc_x + line_margin_x
        length_ratio = [0.75, 0.60, 0.45][i]
        lx_end = doc_x + line_margin_x + (doc_w - 2 * line_margin_x) * length_ratio
        if ly + lw < doc_y + doc_h - line_margin_x:
            draw.line([(lx_start, ly), (lx_end, ly)], fill=line_color, width=lw)

    # Small bar chart at bottom of document (analysis feel)
    bar_base_y = doc_y + doc_h - s * 0.04
    bar_x_start = doc_x + line_margin_x
    bar_w = s * 0.025
    bar_gap = s * 0.015
    bar_heights = [s * 0.04, s * 0.07, s * 0.05]
    bar_colors = [BILI_BLUE, (0, 180, 100), (255, 150, 0)]

    for i, (bh, bc) in enumerate(zip(bar_heights, bar_colors)):
        bx = bar_x_start + i * (bar_w + bar_gap)
        by = bar_base_y - bh
        if by > doc_y + s * 0.06 and bx + bar_w < doc_x + doc_w - line_margin_x:
            draw.rectangle([bx, by, bx + bar_w, bar_base_y], fill=bc)

    # Downscale with high-quality resampling
    img = img.resize((size, size), Image.LANCZOS)
    return img


def main():
    sizes = [16, 48, 128]
    base_path = "/Users/liangliwei/bili-analyzer/extension/icons"

    for size in sizes:
        icon = generate_icon(size)
        path = f"{base_path}/icon{size}.png"
        icon.save(path, "PNG")
        print(f"Created {path} ({size}x{size})")

    print("All icons generated successfully.")


if __name__ == "__main__":
    main()
