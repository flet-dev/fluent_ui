"""Rebuild fonts/FluentIcons.ttf and fonts/SegoeIcons.ttf from MIT-licensed glyphs.

fluent_ui's widgets draw their icons from two bundled Microsoft fonts:
FluentIcons.ttf (Fabric MDL2 Assets) and SegoeIcons.ttf (Segoe Fluent Icons).
Neither one comes with a license that allows redistributing it in apps.

This script replaces both fonts with small fonts cut from Microsoft's
MIT-licensed Fluent UI System Icons
(https://github.com/microsoft/fluentui-system-icons). For every
`FluentIcons.<name>` and `WindowsIcons.<name>` glyph that the widgets in `lib/`
use, it puts the equivalent Fluent UI System Icons glyph at the original
codepoint. Family names and codepoints don't change, so no Dart code changes.

Each replacement glyph is scaled and centered to the bounding box of the
glyph it replaces, so the icons keep their size and position in the widgets.
The bounding boxes are measured from the original fonts, read from git
(`--reference-ref`, `master` by default).

Usage, from the repository root:

    uvx --with fonttools python tool/build_mit_icon_fonts.py

The script fails if a glyph used in `lib/` has no Fluent UI System Icons
equivalent. Add it to MAPPING and run the script again.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.request
from io import BytesIO
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

# microsoft/fluentui-system-icons commit to take the glyphs from.
FSI_COMMIT = "a3de63245b4fa49c30e20d9838593a105affe774"
FSI_URL = (
    "https://raw.githubusercontent.com/microsoft/fluentui-system-icons/"
    f"{FSI_COMMIT}/fonts/FluentSystemIcons-Resizable"
)

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "tool" / ".cache"

# (Dart class, generated Dart file, font family, font file)
SETS = (
    ("FluentIcons", "lib/src/icons.dart", "FluentIcons", "fonts/FluentIcons.ttf"),
    (
        "WindowsIcons",
        "lib/src/windows_icons.dart",
        "SegoeIcons",
        "fonts/SegoeIcons.ttf",
    ),
)

# Generated files that declare the icons, not use them.
DECLARATIONS = {
    "lib/src/icons.dart",
    "lib/src/windows_icons.dart",
    "lib/windows_icon_fallback.dart",
}

# fluent_ui glyph name -> (Fluent UI System Icons name, style).
# A name that isn't listed maps to the same name in the regular style.
MAPPING: dict[str, tuple[str, str]] = {
    "back": ("arrow_left", "regular"),
    "caret_down_solid8": ("caret_down", "filled"),
    "caret_left_solid8": ("caret_left", "filled"),
    "caret_right_solid8": ("caret_right", "filled"),
    "caret_up_solid8": ("caret_up", "filled"),
    "check_mark": ("checkmark", "regular"),
    "chrome_close": ("dismiss", "regular"),
    "clear": ("dismiss", "regular"),
    "completed_solid": ("checkmark_circle", "filled"),
    "critical_error_solid": ("error_circle", "filled"),
    "favorite_star": ("star", "regular"),
    "favorite_star_fill": ("star", "filled"),
    "global_nav_button": ("navigation", "regular"),
    "info_solid": ("info", "filled"),
    "more": ("more_horizontal", "regular"),
    "paste": ("clipboard_paste", "regular"),
    "radio_bullet": ("circle", "filled"),
    "red_eye": ("eye", "regular"),
    "status_error_full": ("dismiss_circle", "filled"),
    "undo": ("arrow_undo", "regular"),
}

ICON_DECL = re.compile(
    r"static const IconData (\w+) = IconData\(\s*0x([0-9a-fA-F]+)", re.M
)


def fsi_file(ext: str) -> Path:
    """Return a Fluent UI System Icons Resizable file (.ttf or .json), downloading it once."""
    path = CACHE / f"FluentSystemIcons-Resizable-{FSI_COMMIT[:12]}{ext}"
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {FSI_URL}{ext}")
        with urllib.request.urlopen(FSI_URL + ext) as response:
            path.write_bytes(response.read())
    return path


def fsi_glyph_names(font: TTFont) -> dict[str, str]:
    """Return icon name -> glyph name for the Resizable font.

    Names come from the font's JSON, not its glyph names: some icons are
    aliases that share another icon's glyph, for example `navigation_20_regular`
    is drawn by the `text_align_justify_20_regular` glyph.
    """
    cmap = font.getBestCmap()
    codes = json.loads(fsi_file(".json").read_text(encoding="utf-8"))
    return {name: cmap[code] for name, code in codes.items() if code in cmap}


def codepoints(dart_file: str) -> dict[str, int]:
    text = (ROOT / dart_file).read_text(encoding="utf-8")
    return {name: int(code, 16) for name, code in ICON_DECL.findall(text)}


def used_glyphs() -> dict[str, set[str]]:
    """Return the glyph names each icon class is used with in lib/, comments excluded."""
    used: dict[str, set[str]] = {cls: set() for cls, *_ in SETS}
    pattern = re.compile(r"\b(%s)\.([a-z_0-9]+)\b" % "|".join(used))
    for path in sorted((ROOT / "lib").rglob("*.dart")):
        if path.relative_to(ROOT).as_posix() in DECLARATIONS:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            code = line.split("//", 1)[0]
            for cls, name in pattern.findall(code):
                used[cls].add(name)
    return used


def reference_font(ref: str, font_file: str) -> TTFont:
    """Return the original font from git, used to measure glyph bounding boxes."""
    data = subprocess.run(
        ["git", "show", f"{ref}:{font_file}"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    font = TTFont(BytesIO(data))
    # The originals have over a thousand glyphs; the rebuilt fonts have a few dozen.
    if len(font.getGlyphOrder()) < 1000:
        raise SystemExit(
            f"{ref}:{font_file} is not the original Microsoft font; "
            "pass --reference-ref with a commit that has it"
        )
    return font


def bounds(glyph_set, glyph_name: str):
    pen = BoundsPen(glyph_set)
    glyph_set[glyph_name].draw(pen)
    return pen.bounds


def build_font(
    family: str,
    glyphs: dict[str, tuple[int, str]],
    source: TTFont,
    reference: TTFont,
) -> TTFont:
    """Build a font with the FSI glyph for each `name -> (codepoint, fsi_glyph)`."""
    src_glyphs = source.getGlyphSet()
    ref_glyphs = reference.getGlyphSet()
    ref_cmap = reference.getBestCmap()
    upm = reference["head"].unitsPerEm
    ascent = reference["hhea"].ascent
    descent = reference["hhea"].descent

    order = [".notdef"]
    cmap: dict[int, str] = {}
    outlines = {".notdef": TTGlyphPen(None).glyph()}
    metrics = {".notdef": (upm, 0)}

    for name, (code, fsi_glyph) in sorted(glyphs.items()):
        rx0, ry0, rx1, ry1 = bounds(ref_glyphs, ref_cmap[code])
        sx0, sy0, sx1, sy1 = bounds(src_glyphs, fsi_glyph)
        scale = min((rx1 - rx0) / (sx1 - sx0), (ry1 - ry0) / (sy1 - sy0))
        dx = (rx0 + rx1) / 2 - (sx0 + sx1) / 2 * scale
        dy = (ry0 + ry1) / 2 - (sy0 + sy1) / 2 * scale

        pen = TTGlyphPen(None)
        src_glyphs[fsi_glyph].draw(TransformPen(pen, (scale, 0, 0, scale, dx, dy)))
        glyph_name = f"{name}_u{code:04X}"
        order.append(glyph_name)
        outlines[glyph_name] = pen.glyph()
        metrics[glyph_name] = (upm, 0)
        cmap[code] = glyph_name

    fb = FontBuilder(upm, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(outlines)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ascent, descent=descent)
    fb.setupOS2(
        sTypoAscender=ascent,
        sTypoDescender=descent,
        sTypoLineGap=0,
        usWinAscent=ascent,
        usWinDescent=-descent,
    )
    fb.setupNameTable(
        {
            "familyName": family,
            "styleName": "Regular",
            "copyright": "Copyright (c) Microsoft Corporation",
            "description": (
                "Glyphs from Fluent UI System Icons "
                f"(microsoft/fluentui-system-icons@{FSI_COMMIT[:12]}), "
                "placed at fluent_ui's codepoints."
            ),
            "licenseDescription": "MIT License",
            "licenseInfoURL": (
                "https://github.com/microsoft/fluentui-system-icons/blob/main/LICENSE"
            ),
        }
    )
    fb.setupPost()
    return fb.font


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--reference-ref",
        default="master",
        help="git ref with the original Microsoft fonts (default: master)",
    )
    args = parser.parse_args()

    source = TTFont(fsi_file(".ttf"))
    fsi_names = fsi_glyph_names(source)
    used = used_glyphs()
    missing = []

    for cls, dart_file, family, font_file in SETS:
        codes = codepoints(dart_file)
        glyphs: dict[str, tuple[int, str]] = {}
        for name in sorted(used[cls]):
            fsi_name, style = MAPPING.get(name, (name, "regular"))
            fsi_icon = f"ic_fluent_{fsi_name}_20_{style}"
            if name not in codes:
                missing.append(f"{cls}.{name}: not declared in {dart_file}")
            elif fsi_icon not in fsi_names:
                missing.append(f"{cls}.{name}: no icon {fsi_icon}")
            else:
                glyphs[name] = (codes[name], fsi_names[fsi_icon])
        if missing:
            continue

        font = build_font(family, glyphs, source, reference_font(args.reference_ref, font_file))
        out = ROOT / font_file
        font.save(out)
        print(f"{font_file}: {len(glyphs)} glyphs, {out.stat().st_size / 1000:.1f} KB")
        for name, (code, fsi_glyph) in sorted(glyphs.items()):
            print(f"  {cls}.{name} (U+{code:04X}) <- {fsi_glyph}")

    if missing:
        raise SystemExit("Unmapped glyphs, add them to MAPPING:\n  " + "\n  ".join(missing))


if __name__ == "__main__":
    main()
