#!/usr/bin/env python3
"""
Floor Plan Preprocessing Script - Line Cleanup
================================================
Cleans unneeded lines from the A-619 Mechanical 2 Floor Plan (Doors & Windows Tags)
so that door/window counting is possible without visual clutter.

Two complementary approaches are used:

1. PDF Layer (OCG) visibility: Turns off unneeded layers so that conforming
   PDF viewers (Adobe Acrobat, browsers) hide them automatically.

2. Content-stream stripping: Physically removes the marked-content sections
   (BDC/EMC blocks) for unwanted layers from the raw PDF content streams,
   so the cleanup is visible even in renderers that ignore OCG state.

Layers / content REMOVED:
  - Grid lines and column grid axes (GRID LINE 2 group)
  - Column grid dimensions and reference numbers
  - Elevation and section tags
  - Grid annotation text
  - Plot limit / setback text
  - Dimension annotations
  - Cloud revision marks
  - Concrete hatching patterns (AD-HAT-CONC)
  - Column tone fill patterns from roof level cross-reference (EC-TONE)
  - Title block content (TBLOCK DM group)
  - GFC (Good For Construction) stamp
  - Room tag outline boxes

Layers / content KEPT:
  - Structural walls (A_A_BLCKWALL Cut)
  - Door geometry (A_A_DOOR)
  - Door tags (A-DOOR-TAG)
  - Window tags (A-WIND-TAG)
  - Slab and room boundaries (A-Slab Limit Line)
  - Room names (A-ROOM-TAG)
  - Floor plan text labels (A_TEXT, text, mTEXT_)
  - Stair geometry, loft elements
  - Glazing / glass elements (14-GLAS)
  - Column and wall outlines (EC-WALL)
  - Vertical fins, stone cladding, expansion joints
  - Track indicators for sliding elements (TRACKS)
"""

import fitz  # PyMuPDF
import os
import re
import sys


# ── Layer removal list ────────────────────────────────────────────────────────

# Layers to remove — matched by substring on layer name (case-insensitive)
REMOVE_PATTERNS = [
    "GRID LINE",       # All grid line group layers (axes, dims, text, annotations)
    "A_GRID",          # Grid axes lines
    "A_L_AXS",         # Axis lines
    "A_AXES GRID",     # Axes grid
    "A_GRID DIM",      # Grid dimensions
    "A_GRID NO.",      # Grid reference numbers
    "A-ELEV. TAG",     # Elevation tags
    "A-SEC. TAG",      # Section tags
    "A-TEXT1",         # Grid annotation text
    "A -TEXT 1",       # Grid annotation text variant
    "plot limit",      # Plot limit / setback text
    "A-dimensions",    # Dimension lines (standalone and within grid)
    "A-CLOUD",         # Cloud revision marks
    "TBLOCK DM",       # Title block (all sub-layers)
    "GFC STAMP",       # Good For Construction stamp
    "AD-HAT-CONC",     # Concrete hatching fill pattern
    "A-ROOM-TAG-BOX",  # Room tag outline boxes (keep text, remove boxes)
    "EC-TONE",         # Column tone fill patterns (roof reference cross-hatching)
]


def layer_should_remove(name: str) -> bool:
    """Return True if this layer should be hidden."""
    nl = name.lower()
    return any(pat.lower() in nl for pat in REMOVE_PATTERNS)


def _build_tag_removal_set(doc: fitz.Document, page: fitz.Page) -> set:
    """
    Build the set of content-stream OCG tag names (e.g. '/oc422') that
    correspond to layers we want to remove.
    """
    ocgs = doc.get_ocgs()
    props_raw = doc.xref_get_key(page.xref, "Resources/Properties")
    if not props_raw or props_raw[0] not in ("dict", "<<"):
        return set()

    _, props_str = props_raw
    tag_to_xref: dict[str, int] = {}
    for m in re.finditer(r"/(\w+)\s+(\d+)\s+0\s+R", props_str):
        tag_to_xref[m.group(1)] = int(m.group(2))

    remove_tags: set[str] = set()
    for tag, xref in tag_to_xref.items():
        name = ocgs.get(xref, {}).get("name", "")
        if layer_should_remove(name):
            remove_tags.add(tag)

    return remove_tags


def _strip_content_streams(doc: fitz.Document, page: fitz.Page,
                            remove_tags: set) -> tuple[int, int]:
    """
    Physically remove BDC/EMC marked-content sections for the given OCG tags
    from all content streams on the page.

    Returns (total_sections_removed, total_bytes_removed).
    """
    total_sections = 0
    total_bytes = 0

    for stream_xref in page.get_contents():
        raw_bytes = doc.xref_stream(stream_xref)
        content = raw_bytes.decode("latin-1")
        original_len = len(content)

        for tag in remove_tags:
            pattern = r"/OC\s+/" + re.escape(tag) + r"\s+BDC.*?EMC\n?"
            sections = len(re.findall(pattern, content, flags=re.DOTALL))
            total_sections += sections
            content = re.sub(pattern, "", content, flags=re.DOTALL)

        bytes_removed = original_len - len(content)
        if bytes_removed > 0:
            total_bytes += bytes_removed
            doc.update_stream(stream_xref, content.encode("latin-1"))

    return total_sections, total_bytes


def clean_floor_plan(input_pdf: str, output_pdf: str) -> dict:
    """
    Clean the floor plan PDF:
      1. Set OCG layer visibility (for conforming PDF viewers).
      2. Strip BDC/EMC content blocks from content streams (for all renderers).

    Returns a summary dict.
    """
    doc = fitz.open(input_pdf)
    page = doc[0]
    ocgs = doc.get_ocgs()

    # ── Step 1: OCG layer visibility ─────────────────────────────────────────
    on_xrefs, off_xrefs = [], []
    kept_names, removed_names = [], []

    for xref, info in sorted(ocgs.items()):
        name = info["name"]
        if layer_should_remove(name):
            off_xrefs.append(xref)
            removed_names.append(name)
        else:
            on_xrefs.append(xref)
            kept_names.append(name)

    doc.set_layer(
        -1,
        basestate="ON",
        on=on_xrefs or None,
        off=off_xrefs or None,
    )

    # ── Step 2: Content-stream stripping ─────────────────────────────────────
    remove_tags = _build_tag_removal_set(doc, page)
    sections_removed, bytes_removed = _strip_content_streams(
        doc, page, remove_tags
    )

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


def render_preview(pdf_path: str, png_path: str, zoom: float = 1.0) -> None:
    """Render the first page of a PDF to a PNG file."""
    doc = fitz.open(pdf_path)
    page = doc[0]
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    pix.save(png_path)
    doc.close()
    print(f"  Saved: {png_path} ({pix.width}x{pix.height} px)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))

    input_pdf = os.path.join(
        "/home/ubuntu/.cursor/projects/workspace/uploads",
        "A-619_Mechanical_2_Floor_Plan-Doors___Windows_Tags-A-619.pdf",
    )
    output_pdf = os.path.join(base_dir, "cleaned_floor_plan.pdf")
    preview_original = os.path.join(base_dir, "preview_original.png")
    preview_cleaned = os.path.join(base_dir, "preview_cleaned.png")

    if not os.path.exists(input_pdf):
        print(f"ERROR: Input PDF not found: {input_pdf}")
        sys.exit(1)

    print("=" * 65)
    print("Floor Plan Line Cleanup  –  Preprocessing for Door/Window Count")
    print("=" * 65)
    print(f"Input:  {input_pdf}")
    print(f"Output: {output_pdf}")
    print()

    print("Rendering original preview ...")
    render_preview(input_pdf, preview_original, zoom=1.0)

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

    print("\nRendering cleaned preview ...")
    render_preview(output_pdf, preview_cleaned, zoom=1.0)

    print()
    print("=" * 65)
    print("Done.")
    print(f"  Cleaned PDF : {output_pdf}")
    print(f"  Original PNG: {preview_original}")
    print(f"  Cleaned PNG : {preview_cleaned}")
    print("=" * 65)


if __name__ == "__main__":
    main()
