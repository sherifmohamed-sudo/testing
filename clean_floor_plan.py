#!/usr/bin/env python3
"""
Floor Plan Preprocessing Script - Line Cleanup
================================================
Cleans unneeded lines from architectural floor plan PDFs (Doors & Windows Tags
sheets) so that door/window counting is possible without visual clutter.

Two complementary approaches are used:

1. PDF Layer (OCG) visibility: Turns off unneeded layers so that conforming
   PDF viewers (Adobe Acrobat, browsers) hide them automatically.

2. Content-stream stripping: Physically removes the marked-content sections
   (BDC/EMC blocks) for unwanted layers from the raw PDF content streams,
   so the cleanup is visible even in renderers that ignore OCG state.

Usage:
    python3 clean_floor_plan.py [input.pdf] [output_prefix]

    If no arguments are given, defaults to the A-619 file in the uploads folder.

Layers / content REMOVED (universal rules):
  - Column grid lines, axes, dimensions, grid reference numbers
  - Elevation and section cut tags
  - Plot limit / setback text
  - Dimension annotations
  - Cloud revision marks
  - Concrete and wall hatching patterns
  - Column tone fill cross-references
  - Title block content (logos, revision table, company info)
  - GFC stamp (Good For Construction)
  - Room tag outline boxes
  - Landscape / planting layers (trees, shrubs, planting patterns, water)
  - Furniture and moveable equipment layers
  - Finishing / floor material layers
  - Plumbing layout layers
  - Structural hatch fill layers
  - French façade detail layers (Vitrocsa, ALU profiles, HACHURES, etc.)
  - OST (object style) override layers
  - Fire-exit stair steps and handrail annotations
  - Void hatch patterns

Layers / content KEPT:
  - Structural walls (A_A_BLCKWALL Cut, A-WALL FILL, EC-WALL)
  - Door geometry (A_A_DOOR) and door tags (A-DOOR-TAG)
  - Window / glazing geometry (Gl-glass, VERRE, 14-GLAS) and tags (A-WIND-TAG)
  - Room names (A-ROOM-TAG)
  - Floor plan text labels (A_TEXT, text, mTEXT_, TEXTE)
  - Slab / room boundaries
  - Stair geometry (Stair Tread, AR-STAIR, exit stairs)
  - Column outlines (A-STRUCT)
  - Expansion joints (A_E_EXP)
  - Stone cladding and vertical fins (facade reference only)
"""

import fitz  # PyMuPDF
import os
import re
import sys
from pathlib import Path


# ── Layer removal list ────────────────────────────────────────────────────────

# Layers to remove — matched by case-insensitive substring on the full layer name
REMOVE_PATTERNS = [
    # ── Grid / annotation ───────────────────────────────────────────────────
    "GRID LINE",          # All GRID LINE 2 sub-layers
    "A_GRID",             # Grid axes lines
    "A_L_AXS",            # Axis lines
    "A_AXES GRID",
    "A_GRID DIM",
    "A_GRID NO.",
    "A-ELEV. TAG",        # Elevation tags
    "A-SEC. TAG",         # Section cut tags
    "A-TEXT1",            # Grid annotation text
    "A -TEXT 1",
    "plot limit",         # Plot limit / setback text
    "A-dimensions",       # Dimension lines (standalone + grid sub-layer)
    "DIMENSIONS",         # General dimensions layer
    "A-CLOUD",            # Cloud revision marks
    "A-ARROW",            # Arrow annotations (not door swings)
    "COTES TECHNIQUES",   # French technical dimension annotations

    # ── Title block / stamps ────────────────────────────────────────────────
    "TBLOCK DM",          # Title block group (logos, revisions, lines, text)
    "GFC STAMP",          # Good For Construction stamp
    "A_T_TEXT",           # Title text on drawing sheet (sheet title overlay)

    # ── Hatching / fill patterns ────────────────────────────────────────────
    "AD-HAT-CONC",        # Concrete hatching
    "EC-TONE",            # Column tone fill cross-references
    "A-VOIDHATCH",        # Void/opening hatch
    "A_L_HAT_WALL",       # Wall hatching
    "TA - HACH",          # Landscape/architectural hatching
    "HACHURES PROFILS",   # Profile hatch (façade)
    "HACHURES VERRE",     # Glass hatch (façade)
    "HACHURES",           # Generic hatch (façade)
    "A-HATCH",            # Structural hatch fills
    "TA - WALL HATCH",    # Wall hatch fills
    "HATCH",              # Generic hatch
    "A-WALL FILL",        # Wall fill solid tones  — remove; walls are shown by outlines

    # ── Furniture / equipment ───────────────────────────────────────────────
    "TA - MOBILIER",      # French: furniture
    "TA-MOBILIER",
    "A-FURN",             # Furniture
    "A-LIFT",             # Lift / elevator symbol
    "A-SYMB-MISC",        # Miscellaneous symbols
    "TA - WOODWORK",      # Woodwork furniture
    "TA - WOOD WORK",
    "F-FGHT-EQ",          # Fire-fighting equipment
    "mechanical requirments",  # Mechanical requirements text

    # ── Landscape / planting ────────────────────────────────────────────────
    "XR Landscape",       # Entire landscape xref group
    "L-WATER",            # Water / pool
    "L-PL-PATT",          # Planting pattern
    "L-PL-SHRUB",         # Shrubs
    "L-PLANT",            # Plants
    "L-LO-WALL",          # Landscape low walls
    "L-LO-PV PATT",       # Paving pattern
    "L-LO-POOL",          # Pool landscape
    "L-PL-TREE",          # Trees

    # ── Floor finishes / materials ──────────────────────────────────────────
    "TA - FLOOR",         # Floor finish pattern
    "TA - WALL",          # Wall finish pattern
    "A-FINISH",           # Finish layers
    "A_I_FF",             # Finish fill
    "02 - TA - BS - TOPFLOOR FLOOR",  # Top floor finish

    # ── Plumbing ────────────────────────────────────────────────────────────
    "TA - PLUMBING",      # Plumbing layout

    # ── Façade detail (Vitrocsa, French curtain-wall) ───────────────────────
    "PROFIL ALU",         # Aluminium profile detail
    "ISOLATION Vitrocsa", # Vitrocsa glazing insulation
    "RAHMEN025",          # Frame detail
    "JOINT",              # Sealant joint
    "LOQUET",             # Latch detail
    "COLLE-SCOTCH",       # Tape/glue detail
    "SILICONE",           # Silicone bead
    "AXES",               # Detail axes
    "CACHE",              # Cover/cap profiles
    "VIOLET PRINTED",     # Print colour overlay
    "PROFIL ALU",         # (duplicate guard)

    # ── OST / override styles ───────────────────────────────────────────────
    "WALL-OST",
    "0-OST",
    "ID-OST",

    # ── Misc annotations to suppress ───────────────────────────────────────
    "A-ROOM-TAG-BOX",     # Room tag bounding boxes (keep text, not boxes)
    "A-Stair Hidden",     # Hidden line stair projection (dashed, confusing)
    "A-upper-dot",        # Upper level dot marker
    "YELLOW",             # Highlight / colour overlay
    "brace",              # Brace symbol
    "A-F.EXIT STAIR STEPS",    # Fire-exit stair steps
    "A-F.EXIT STAIR HANDRAIL", # Fire-exit stair handrail
    "XR 2nd Floor Plan",       # 2nd floor plan xref ghost
    "A-117_Roof",              # REV 01 old roof plan xref
]


def layer_should_remove(name: str) -> bool:
    """Return True if this layer should be removed from the cleaned output."""
    nl = name.lower()
    return any(pat.lower() in nl for pat in REMOVE_PATTERNS)


def _build_tag_removal_set(doc: fitz.Document, page: fitz.Page) -> set:
    """Map content-stream OCG resource names (e.g. 'oc422') to removal decisions."""
    ocgs = doc.get_ocgs()
    props_raw = doc.xref_get_key(page.xref, "Resources/Properties")
    if not props_raw or props_raw[0] not in ("dict", "<<"):
        return set()

    _, props_str = props_raw
    tag_to_xref: dict[str, int] = {}
    for m in re.finditer(r"/(\w+)\s+(\d+)\s+0\s+R", props_str):
        tag_to_xref[m.group(1)] = int(m.group(2))

    return {
        tag for tag, xref in tag_to_xref.items()
        if layer_should_remove(ocgs.get(xref, {}).get("name", ""))
    }


def _strip_content_streams(doc: fitz.Document, page: fitz.Page,
                            remove_tags: set) -> tuple[int, int]:
    """
    Physically delete BDC/EMC marked-content sections for the given OCG tags
    from every content stream on the page.
    Returns (sections_removed, bytes_removed).
    """
    total_sections, total_bytes = 0, 0

    for stream_xref in page.get_contents():
        raw = doc.xref_stream(stream_xref).decode("latin-1")
        original_len = len(raw)

        for tag in remove_tags:
            pattern = r"/OC\s+/" + re.escape(tag) + r"\s+BDC.*?EMC\n?"
            found = re.findall(pattern, raw, flags=re.DOTALL)
            total_sections += len(found)
            raw = re.sub(pattern, "", raw, flags=re.DOTALL)

        removed = original_len - len(raw)
        if removed > 0:
            total_bytes += removed
            doc.update_stream(stream_xref, raw.encode("latin-1"))

    return total_sections, total_bytes


def clean_floor_plan(input_pdf: str, output_pdf: str) -> dict:
    """
    Run the two-stage cleaning pipeline on input_pdf and write output_pdf.
    Returns a summary dict.
    """
    doc = fitz.open(input_pdf)
    page = doc[0]
    ocgs = doc.get_ocgs()

    on_xrefs, off_xrefs, kept_names, removed_names = [], [], [], []
    for xref, info in sorted(ocgs.items()):
        name = info["name"]
        if layer_should_remove(name):
            off_xrefs.append(xref)
            removed_names.append(name)
        else:
            on_xrefs.append(xref)
            kept_names.append(name)

    doc.set_layer(-1, basestate="ON",
                  on=on_xrefs or None, off=off_xrefs or None)

    remove_tags = _build_tag_removal_set(doc, page)
    sections_removed, bytes_removed = _strip_content_streams(doc, page, remove_tags)

    doc.save(output_pdf, garbage=4, deflate=True)
    doc.close()

    return {
        "kept_count": len(kept_names),
        "removed_count": len(removed_names),
        "kept": kept_names,
        "removed": removed_names,
        "content_sections_removed": sections_removed,
        "content_bytes_removed": bytes_removed,
    }


def render_high_res(pdf_path: str, png_path: str, zoom: float = 4.0) -> tuple[int, int]:
    """
    Render the first page at `zoom`x and save a tight-cropped PNG.
    Returns (width, height) of the saved image.
    """
    doc = fitz.open(pdf_path)
    page = doc[0]
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)

    # Tight-crop: find bounding box of non-white content
    import numpy as np
    from PIL import Image as PILImage

    arr = __import__("numpy").frombuffer(pix.samples, dtype="uint8").reshape(
        pix.height, pix.width, 3)
    non_white = (arr < 240).any(axis=2)
    rows = non_white.any(axis=1)
    cols = non_white.any(axis=0)

    if rows.any() and cols.any():
        rmin, rmax = int(non_white.any(axis=1).argmax()), \
                     int(pix.height - 1 - non_white.any(axis=1)[::-1].argmax())
        cmin, cmax = int(non_white.any(axis=0).argmax()), \
                     int(pix.width - 1 - non_white.any(axis=0)[::-1].argmax())
        pad = int(40 * zoom)
        r0 = max(0, rmin - pad)
        r1 = min(pix.height, rmax + pad)
        c0 = max(0, cmin - pad)
        c1 = min(pix.width, cmax + pad)
        arr = arr[r0:r1, c0:c1]

    img = PILImage.fromarray(arr, "RGB")
    img.save(png_path, optimize=True)
    doc.close()
    return img.size


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    base_dir = Path(__file__).parent

    if len(sys.argv) >= 2:
        input_pdf = sys.argv[1]
        stem = Path(input_pdf).stem
    else:
        input_pdf = str(
            Path("/home/ubuntu/.cursor/projects/workspace/uploads") /
            "A-619_Mechanical_2_Floor_Plan-Doors___Windows_Tags-A-619.pdf"
        )
        stem = "A-619"

    if len(sys.argv) >= 3:
        stem = sys.argv[2]

    output_pdf    = str(base_dir / f"{stem}_cleaned.pdf")
    out_original  = str(base_dir / f"{stem}_original.png")
    out_cleaned   = str(base_dir / f"{stem}_cleaned.png")

    if not Path(input_pdf).exists():
        print(f"ERROR: Input PDF not found: {input_pdf}")
        sys.exit(1)

    print("=" * 65)
    print("Floor Plan Line Cleanup  –  Preprocessing for Door/Window Count")
    print("=" * 65)
    print(f"Input:  {input_pdf}")
    print(f"Output: {output_pdf}")
    print()

    print("Rendering original (high-res) ...")
    w, h = render_high_res(input_pdf, out_original, zoom=4.0)
    print(f"  Saved: {out_original} ({w}x{h} px)")

    print("\nCleaning floor plan layers ...")
    summary = clean_floor_plan(input_pdf, output_pdf)

    print(f"\nLayers KEPT  ({summary['kept_count']}):")
    for name in summary["kept"]:
        print(f"  + {name}")
    print(f"\nLayers REMOVED ({summary['removed_count']}):")
    for name in summary["removed"]:
        print(f"  - {name}")
    print(f"\nContent stream sections stripped : {summary['content_sections_removed']}")
    print(f"Content bytes removed            : {summary['content_bytes_removed']:,}")

    print("\nRendering cleaned (high-res) ...")
    w, h = render_high_res(output_pdf, out_cleaned, zoom=4.0)
    print(f"  Saved: {out_cleaned} ({w}x{h} px)")

    print()
    print("=" * 65)
    print("Done.")
    print(f"  Cleaned PDF : {output_pdf}")
    print(f"  Original PNG: {out_original}")
    print(f"  Cleaned PNG : {out_cleaned}")
    print("=" * 65)


if __name__ == "__main__":
    main()
