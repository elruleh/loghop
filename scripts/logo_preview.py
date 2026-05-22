#!/usr/bin/env python3
"""Preview loghop logo gradients. Run in a truecolor terminal."""

import pyfiglet

base = pyfiglet.figlet_format("loghop", font="slant").rstrip("\n")

GLYPH_CHARS = set(r'/\\_|.,`\'"-~!()<>abcdefghijklmnopqrstuvwxyz0123456789')
FULL = "\u2588"

lines = base.split("\n")
filled = []
for line in lines:
    filled_line = ""
    for c in line:
        filled_line += FULL if c in GLYPH_CHARS else c
    filled.append(filled_line)

max_width = max(len(line_text) for line_text in filled)
BOLD = "\033[1m"
RESET = "\033[0m"
DIM = "\033[2m"


def lerp(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2, strict=False))


def gradient(line_idx, col_idx, palette, direction):
    if direction == "diagonal":
        t = ((line_idx / max(len(filled) - 1, 1)) + (col_idx / max(max_width - 1, 1))) / 2
    else:
        t = col_idx / max(max_width - 1, 1)
    seg = t * (len(palette) - 1)
    i = int(seg)
    f = seg - i
    if i >= len(palette) - 1:
        return palette[-1]
    return lerp(palette[i], palette[i + 1], f)


PALETTES = {
    "1. cyan → purple (diagonal)": [
        (0, 215, 255),
        (56, 189, 248),
        (99, 102, 241),
        (139, 92, 246),
        (168, 85, 247),
    ],
    "2. cyan → purple (horizontal)": [
        (0, 215, 255),
        (56, 189, 248),
        (99, 102, 241),
        (139, 92, 246),
        (168, 85, 247),
    ],
    "3. cyan monochrome (horizontal)": [
        (0, 215, 255),
        (0, 188, 212),
        (0, 151, 167),
        (0, 131, 143),
        (0, 105, 114),
    ],
    "4. sunset (diagonal)": [
        (0, 215, 255),
        (168, 85, 247),
        (236, 72, 153),
        (249, 115, 22),
        (245, 158, 11),
    ],
    "5. teal → amber (diagonal)": [
        (6, 182, 212),
        (20, 184, 166),
        (34, 197, 94),
        (132, 204, 22),
        (234, 179, 8),
    ],
    "6. brand fade (diagonal)": [
        (0, 200, 240),
        (0, 180, 220),
        (0, 160, 200),
        (0, 140, 180),
        (0, 120, 160),
    ],
    "7. solid cyan (no gradient)": [
        (0, 200, 240),
    ],
}

for name, palette in PALETTES.items():
    direction = "diagonal" if "diagonal" in name else "horizontal"
    if len(palette) == 1:
        direction = "horizontal"

    print(f"\n{'=' * 50}")
    print(f"  {name}")
    print(f"{'=' * 50}\n")

    for row, line in enumerate(filled):
        out = ""
        for col, c in enumerate(line):
            if c == FULL:
                r, g, b = gradient(row, col, palette, direction)
                out += f"{BOLD}\033[38;2;{r};{g};{b}m{FULL}"
            else:
                out += " "
        out += RESET
        print(out)

    print(f"{DIM}  switch AI coding assistants without starting over{RESET}\n")
