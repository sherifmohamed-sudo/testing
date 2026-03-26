# Floor Plan Line Cleanup – Preprocessing for Door/Window Count

This repository contains a preprocessing script that cleans the **A-619 Mechanical 2 Floor Plan (Doors & Windows Tags)** PDF by removing unneeded lines so that doors and windows can be counted reliably.

## What it does

The script removes visual noise from the floor plan while preserving all door and window geometry and tags:

| Removed | Kept |
|---|---|
| Column grid lines (A–M, 01–14) | Structural walls |
| Grid dimensions and bubbles | Door geometry & door tags |
| Elevation / section tags | Window tags |
| Plot limit / setback text | Slab & room boundaries |
| Dimension annotations | Room name labels |
| Cloud revision marks | Stair geometry & glazing |
| Concrete hatching patterns | Floor plan text labels |
| Column tone fill patterns | Vertical fins & cladding |
| Title block (logos, stamps, revisions) | Expansion joints & tracks |
| GFC "Good For Construction" stamp | Proposed column outlines |

## Approach

Two complementary techniques are applied:

1. **PDF Layer (OCG) visibility** – Turns off unneeded Optional Content Groups so that conforming PDF viewers (Adobe Acrobat, browsers) render the cleaned view automatically.

2. **Content-stream stripping** – Physically removes the `BDC/EMC` marked-content blocks for unwanted layers from the raw PDF content streams, ensuring the cleanup is visible in all renderers including PyMuPDF.

## Usage

```bash
pip install -r requirements.txt
python3 clean_floor_plan.py
```

### Output files

| File | Description |
|---|---|
| `cleaned_floor_plan.pdf` | Cleaned PDF with unwanted layers removed |
| `preview_original.png` | Full-page render of the original (for comparison) |
| `preview_cleaned.png` | Full-page render of the cleaned output |

## Requirements

- Python 3.10+
- `pymupdf` ≥ 1.27
- `Pillow` ≥ 10.0 (for preview thumbnails)
