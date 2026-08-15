#!/usr/bin/env python3
"""Validate README patterns that keep the profile usable on narrow screens."""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
readme = README.read_text(encoding="utf-8")
errors: list[str] = []

# Every local image referenced by the README must exist.
for ref in re.findall(r'(?:src|srcset)="(\./assets/[^"?]+)', readme):
    path = ROOT / ref[2:]
    if not path.exists():
        errors.append(f"missing local image: {ref}")

# Wide visual assets must be fluid in the README rather than fixed to a desktop width.
for tag in re.findall(r"<img\b[^>]+>", readme, flags=re.IGNORECASE):
    src = re.search(r'src="([^"?]+)', tag)
    width = re.search(r'width="([^"]+)', tag)
    if not src or not width:
        continue
    value = width.group(1)
    if "./assets/" in src.group(1) and value not in {"100%", "32", "36", "40"}:
        errors.append(f"non-fluid local image width: {src.group(1)} -> {value}")

# Tech icons must stay compact and have both theme variants.
icon_names = set(re.findall(r'assets/icons/([a-z0-9]+)-light\.svg', readme))
for name in sorted(icon_names):
    for suffix in ("light", "dark"):
        path = ROOT / f"assets/icons/{name}-{suffix}.svg"
        if not path.exists():
            errors.append(f"missing theme icon pair: {path}")
    if not re.search(rf'assets/icons/{re.escape(name)}-light\.svg" width="(?:32|36|40)"', readme):
        errors.append(f"icon is not compact: {name}")

# All local SVGs must parse. Accessibility is verified through the README alt text,
# because generated metrics assets can be replaced by GitHub Actions.
for svg in (ROOT / "assets").rglob("*.svg"):
    try:
        ET.parse(svg)
    except ET.ParseError as exc:
        errors.append(f"invalid SVG {svg}: {exc}")

# Prevent accidental desktop-only constructs in the content.
if '<img src="https://skillicons.dev/' in readme:
    errors.append("dynamic desktop icon strip is still present")
if 'width="850"' in readme or 'width="960"' in readme:
    errors.append("fixed desktop metrics width is still present")

if errors:
    print("README mobile check failed:")
    print("\n".join(f"- {item}" for item in errors))
    sys.exit(1)

print(f"README mobile check passed: {len(icon_names)} theme-aware icon pairs and fluid local visuals validated.")
