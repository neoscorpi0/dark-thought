#!/usr/bin/env python3
"""Render terminal-style screenshots and social cards for Dark Thought tools."""
import os
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFont

MONO = "/usr/share/fonts/liberation/LiberationMono-Regular.ttf"
MONO_B = "/usr/share/fonts/liberation/LiberationMono-Bold.ttf"
INK = (11, 15, 20)
BAR = (22, 33, 44)
SOFT = (230, 237, 243)
MUTED = (143, 169, 196)
CYAN = (0, 229, 255)
SKY = (90, 162, 255)
GREEN = (91, 228, 155)


def terminal(lines, out, title="bash", width=1000, pad=22, size=15):
    f = ImageFont.truetype(MONO, size)
    fb = ImageFont.truetype(MONO_B, size)
    lh = int(size * 1.55)
    bar_h = 36
    height = bar_h + pad * 2 + lh * len(lines)
    img = Image.new("RGB", (width, height), INK)
    d = ImageDraw.Draw(img)

    # title bar
    d.rectangle([0, 0, width, bar_h], fill=BAR)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([14 + i * 20, 12, 26 + i * 20, 24], fill=c)
    d.text((width / 2, bar_h / 2), title, font=f, fill=MUTED, anchor="mm")

    y = bar_h + pad
    for line in lines:
        colour = SOFT
        if line.startswith("$"):
            colour = CYAN
        elif line.startswith("#") or line.startswith("//"):
            colour = MUTED
        elif line.strip().startswith("✓") or "OK" in line[:6]:
            colour = GREEN
        d.text((pad, y), line, font=fb if line.startswith("$") else f, fill=colour)
        y += lh

    img.save(out, "PNG")
    return img.size


def card(name, tagline, out, w=1280, h=640):
    img = Image.new("RGB", (w, h), INK)
    d = ImageDraw.Draw(img)
    # subtle grid
    for x in range(0, w, 64):
        d.line([(x, 0), (x, h)], fill=(15, 22, 30))
    for y in range(0, h, 64):
        d.line([(0, y), (w, y)], fill=(15, 22, 30))
    # rings
    cx, cy, r = 240, h // 2, 110
    for cxx, col in ((cx - r * 0.62, CYAN), (cx + r * 0.62, SKY)):
        d.ellipse([cxx - r, cy - r, cxx + r, cy + r], outline=col, width=9)
    d.rectangle([cx - r * 0.62 - r, cy - 6, cx + r * 0.62 + r, cy + 6], fill=INK)

    f_title = ImageFont.truetype(MONO_B, 62)
    f_tag = ImageFont.truetype(MONO, 27)
    f_small = ImageFont.truetype(MONO, 21)
    d.text((470, cy - 40), name.upper(), font=f_title, fill=SOFT)
    d.text((472, cy + 30), tagline, font=f_tag, fill=(186, 204, 222))
    d.text((472, h - 78), "DARK THOUGHT  ·  stdlib only  ·  no cloud  ·  MIT", font=f_small, fill=(120, 190, 255))
    img.save(out, "PNG")
    return (w, h)


if __name__ == "__main__":
    print("helpers only — driven by make_assets.py")
