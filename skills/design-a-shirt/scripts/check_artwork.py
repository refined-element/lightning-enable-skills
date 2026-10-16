#!/usr/bin/env python3
"""check_artwork.py: check a T-shirt PNG against the store's print rules before uploading it.

  python scripts/check_artwork.py design.png
  python scripts/check_artwork.py design.png --color black
  python scripts/check_artwork.py design.png --color "#0c0c0c" --json

Why it exists: the store splits its artwork checks around the design fee (the
custom catalog's ``artworkChecks``). At upload, free: size and declared type,
PNG signature, dimensions and pixel count, decodability, visible content
(NoVisibleContent is refused with 400 nothing_to_print), and the
LowEffectiveDpi, NoTransparency and ExcessiveEmptyMargins warnings (margins
only for artwork with transparency). After Payment A: metadata removal,
colour-profile and animation discard, contrast against the garment and the
final print file; an unprintable file ends in GenerationFailed with failureCode
InvalidInput and keeps the fee. This script runs both sets locally, so the
person sees the after-payment findings (LowContrastWithGarment above all)
before anyone pays. Checking here costs nothing.

Two layers:

* Header checks, standard library only: PNG signature, chunk CRCs, width and
  height, the 40 million pixel cap, file size, effective DPI on the 12 x 16 in
  front print area, whether the file can hold transparency at all, animation
  and embedded color profiles.
* Pixel checks, when Pillow is installed (``pip install Pillow``): whether any
  pixel is actually transparent, whether anything is visible enough to print,
  how much of the canvas is empty margin, and, with ``--color``, how much of the
  artwork has too little contrast with the shirt. Without Pillow the script says
  the pixel checks were skipped; it never guesses.

The thresholds mirror the store's print-file preparation: 150 DPI warning,
visible means alpha 128 or more, background means alpha below 16, more than 40%
empty margin warns, contrast ratio below 1.5 on half the visible artwork warns.

The script reads one local file. It makes no network request and never pays.
Exit status: 0 when the store would accept the file (warnings may still be
listed), 1 when the upload would be refused, 2 for a usage error or a file that
cannot be read or decoded, 3 when the header checks pass but the pixels were
not checked (Pillow is missing). Python 3.10 or later.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import zlib
from dataclasses import dataclass, field
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# From the custom catalog (designRequirements, printAreas) and llms-full.txt.
MIN_WIDTH_PX = 2400
MIN_HEIGHT_PX = 2400
MAX_WIDTH_PX = 12000
MAX_HEIGHT_PX = 12000
MAX_FILE_BYTES = 52_428_800
MAX_TOTAL_PIXELS = 40_000_000
PRINT_AREA_IN = (12, 16)  # front, DTG: width x height

# Print-file preparation thresholds.
LOW_DPI_WARNING = 150
VISIBLE_ALPHA = 128
BACKGROUND_ALPHA = 16
OPAQUE_BACKGROUND_TOLERANCE = 8
EMPTY_MARGIN_WARNING = 0.40
LOW_CONTRAST_RATIO = 1.5
LOW_CONTRAST_FRACTION_WARNING = 0.5

GARMENT_COLORS = {"black": "#0c0c0c", "white": "#ffffff"}

# Color types that carry an alpha channel: 4 is grayscale + alpha, 6 is RGBA.
ALPHA_COLOR_TYPES = {4, 6}


@dataclass
class PngInfo:
    width: int
    height: int
    bit_depth: int
    color_type: int
    interlaced: bool
    has_trns: bool
    animated: bool
    has_icc: bool

    @property
    def can_be_transparent(self) -> bool:
        return self.color_type in ALPHA_COLOR_TYPES or self.has_trns


@dataclass
class Finding:
    code: str
    message: str


@dataclass
class Report:
    path: str
    size_bytes: int
    info: PngInfo | None = None
    effective_dpi: int | None = None
    print_inches: tuple[float, float] | None = None
    refused: list[Finding] = field(default_factory=list)  # refused at upload; nothing is charged
    warnings: list[Finding] = field(default_factory=list)
    pixel_checks: str = "skipped"
    stats: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.refused

    @property
    def pixels_checked(self) -> bool:
        return self.pixel_checks == "done"

    def has(self, code: str) -> bool:
        return any(f.code == code for f in self.refused + self.warnings)


class PngError(ValueError):
    """The bytes are not a readable PNG."""


class ArtworkDecodeError(RuntimeError):
    """The header is valid but Pillow could not decode the pixels: the store refuses it too."""


def parse_png(data: bytes) -> PngInfo:
    """Read the PNG header and chunk list without decoding any pixels."""
    if not data.startswith(PNG_SIGNATURE):
        raise PngError("not a PNG: the file does not start with the PNG signature")
    pos = len(PNG_SIGNATURE)
    ihdr = None
    has_trns = animated = has_icc = has_idat = False
    while pos < len(data):
        if pos + 8 > len(data):
            raise PngError("truncated chunk header")
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        end = pos + 12 + length
        if end > len(data):
            raise PngError(f"chunk {ctype.decode('latin-1')} runs past the end of the file")
        body = data[pos + 8:pos + 8 + length]
        (crc,) = struct.unpack(">I", data[pos + 8 + length:end])
        if zlib.crc32(ctype + body) & 0xFFFFFFFF != crc:
            raise PngError(f"chunk {ctype.decode('latin-1')} has a bad CRC (the file is damaged)")
        if ihdr is None and ctype != b"IHDR":
            raise PngError("the first chunk is not IHDR")
        if ctype == b"IHDR":
            if length != 13:
                raise PngError("IHDR has the wrong length")
            ihdr = struct.unpack(">IIBBBBB", body)
        elif ctype == b"tRNS":
            has_trns = True
        elif ctype == b"acTL":
            animated = True
        elif ctype == b"iCCP":
            has_icc = True
        elif ctype == b"IDAT":
            has_idat = True
        elif ctype == b"IEND":
            break
        pos = end
    if ihdr is None:
        raise PngError("no IHDR chunk")
    if not has_idat:
        raise PngError("no image data (IDAT) chunk")
    width, height, bit_depth, color_type, _compression, _filter, interlace = ihdr
    if width == 0 or height == 0:
        raise PngError("zero width or height")
    return PngInfo(width, height, bit_depth, color_type, interlace == 1, has_trns, animated, has_icc)


def effective_dpi(width: int, height: int) -> tuple[int, tuple[float, float]]:
    """The store's DPI: the image is fitted into 12 x 16 in at its own aspect ratio."""
    area_w, area_h = PRINT_AREA_IN
    exact = max(width / area_w, height / area_h)
    return math.floor(exact), (round(width / exact, 2), round(height / exact, 2))


def header_findings(report: Report, info: PngInfo) -> None:
    w, h = info.width, info.height
    if w < MIN_WIDTH_PX or h < MIN_HEIGHT_PX:
        report.refused.append(Finding(
            "DimensionsTooSmall",
            f"{w} x {h} px; the minimum is {MIN_WIDTH_PX} x {MIN_HEIGHT_PX} px. "
            "Generate or upscale to 3600 x 4800."))
    if w > MAX_WIDTH_PX or h > MAX_HEIGHT_PX:
        report.refused.append(Finding(
            "DimensionsTooLarge", f"{w} x {h} px; the maximum is {MAX_WIDTH_PX:,} px on a side."))
    if w * h > MAX_TOTAL_PIXELS:
        report.refused.append(Finding(
            "TooManyPixels",
            f"{w * h:,} pixels; the store prepares at most {MAX_TOTAL_PIXELS:,}. "
            "Downscale (3600 x 4800 is 17.3 million)."))
    dpi, inches = effective_dpi(w, h)
    report.effective_dpi, report.print_inches = dpi, inches
    if dpi < LOW_DPI_WARNING:
        report.warnings.append(Finding(
            "LowEffectiveDpi",
            f"prints at {dpi} DPI ({inches[0]} x {inches[1]} in); {LOW_DPI_WARNING} or more is "
            "recommended. Use a larger PNG."))
    if not info.can_be_transparent:
        report.warnings.append(Finding(
            "NoTransparency",
            "the PNG has no alpha channel, so its background prints as a solid rectangle. "
            "Export it with a transparent background."))
    if info.animated:
        report.warnings.append(Finding("AnimationDiscarded", "the PNG is animated; only the first frame prints."))
    if info.has_icc:
        report.warnings.append(Finding(
            "ColorProfileDiscarded",
            "an embedded color profile will be removed and colors treated as sRGB. Export in sRGB."))


def luminance(rgb: tuple[int, int, int]) -> float:
    def linear(c: int) -> float:
        v = c / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)


def contrast_ratio(a: float, b: float) -> float:
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def parse_hex(value: str) -> tuple[int, int, int]:
    value = GARMENT_COLORS.get(value.strip().lower(), value.strip())
    if len(value) != 7 or not value.startswith("#"):
        raise ValueError(f"color must be black, white or #rrggbb, not {value!r}")
    try:
        return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)
    except ValueError:
        raise ValueError(f"color must be black, white or #rrggbb, not {value!r}") from None


def pixel_findings(
    report: Report,
    width: int,
    height: int,
    alpha_histogram: list[int],
    content_bbox: tuple[int, int, int, int] | None,
    low_contrast_fraction: float | None = None,
) -> None:
    """Judge the pixel statistics. Pure, so tests feed it numbers; Pillow feeds it in check()."""
    total = width * height
    has_transparency = sum(alpha_histogram[:255]) > 0
    visible = sum(alpha_histogram[VISIBLE_ALPHA:])
    report.pixel_checks = "done"
    report.stats.update(has_transparency=has_transparency, visible_fraction=round(visible / total, 4))
    if visible == 0:
        report.refused.append(Finding(
            "NoVisibleContent",
            "nothing is opaque enough to print (no pixel at 50% alpha or more). The store refuses "
            "it at upload with 400 nothing_to_print; nothing is charged. Make artwork with visible pixels."))
        return
    if not has_transparency and not report.has("NoTransparency"):
        report.warnings.append(Finding(
            "NoTransparency",
            "every pixel is opaque, so the background prints as a solid rectangle. Remove the background."))
    if content_bbox is None:
        margin = 1.0 if has_transparency else 0.0
    else:
        left, top, right, bottom = content_bbox
        margin = 1 - ((right - left) * (bottom - top)) / total
    report.stats["empty_margin_fraction"] = round(margin, 4)
    if margin > EMPTY_MARGIN_WARNING:
        report.warnings.append(Finding(
            "ExcessiveEmptyMargins",
            f"{margin:.0%} of the canvas is empty margin, so the design prints smaller than the "
            "print area. Crop to the artwork, keeping a small border."))
    if low_contrast_fraction is not None:
        report.stats["low_contrast_fraction"] = round(low_contrast_fraction, 4)
        if low_contrast_fraction >= LOW_CONTRAST_FRACTION_WARNING:
            report.warnings.append(Finding(
                "LowContrastWithGarment",
                f"{low_contrast_fraction:.0%} of the visible artwork is too close to the shirt color "
                "to read. Pick the other shirt color or recolor the artwork."))


def pillow_pixel_checks(report: Report, path: Path, garment: str | None) -> None:
    try:
        from PIL import Image, ImageChops
    except ImportError:
        report.pixel_checks = "skipped: Pillow is not installed (pip install Pillow)"
        return
    Image.MAX_IMAGE_PIXELS = MAX_TOTAL_PIXELS + 1
    with Image.open(path) as im:
        im.seek(0)
        rgba = im.convert("RGBA")
    alpha = rgba.getchannel("A")
    hist = alpha.histogram()
    if sum(hist[:255]) > 0:
        bbox = alpha.point(lambda a: 255 if a >= BACKGROUND_ALPHA else 0).getbbox()
    else:
        # Opaque: like the store, treat pixels close to the top-left corner color as background.
        rgb = rgba.convert("RGB")
        corner = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
        bands = ImageChops.difference(rgb, corner).split()
        mask = None
        for band in bands:
            band_mask = band.point(lambda v: 255 if v > OPAQUE_BACKGROUND_TOLERANCE else 0)
            mask = band_mask if mask is None else ImageChops.lighter(mask, band_mask)
        bbox = mask.getbbox() or (0, 0, rgb.width, rgb.height)
    fraction = None
    if garment:
        garment_luminance = luminance(parse_hex(garment))
        small = rgba.copy()
        small.thumbnail((512, 512), Image.Resampling.NEAREST)
        visible = low = 0
        raw = small.tobytes()
        for i in range(0, len(raw), 4):
            r, g, b, a = raw[i], raw[i + 1], raw[i + 2], raw[i + 3]
            if a >= VISIBLE_ALPHA:
                visible += 1
                if contrast_ratio(luminance((r, g, b)), garment_luminance) < LOW_CONTRAST_RATIO:
                    low += 1
        fraction = low / visible if visible else 0.0
    pixel_findings(report, rgba.width, rgba.height, hist, bbox, fraction)


def check(path: Path, garment: str | None = None, pixels: bool = True) -> Report:
    data = path.read_bytes()
    report = Report(path=str(path), size_bytes=len(data))
    if len(data) > MAX_FILE_BYTES:
        report.refused.append(Finding(
            "FileTooLarge", f"{len(data):,} bytes; the maximum is {MAX_FILE_BYTES:,} (50 MB)."))
    try:
        info = parse_png(data)
    except PngError as exc:
        report.refused.append(Finding("NotAReadablePng", f"{exc}. Export the artwork again as PNG."))
        return report
    report.info = info
    header_findings(report, info)
    if pixels and not report.has("TooManyPixels"):
        try:
            pillow_pixel_checks(report, path, garment)
        except Exception as exc:  # noqa: BLE001 - any decoder failure means the same thing
            raise ArtworkDecodeError(f"cannot decode the pixels ({type(exc).__name__}: {exc})") from exc
    return report


def render(report: Report) -> str:
    lines = [f"Artwork check: {report.path}"]
    if report.info:
        info = report.info
        lines.append(
            f"  {info.width} x {info.height} px, {report.size_bytes:,} bytes, "
            f"alpha channel: {'yes' if info.can_be_transparent else 'no'}")
        lines.append(
            f"  effective DPI {report.effective_dpi}; prints about {report.print_inches[0]} x "
            f"{report.print_inches[1]} in (fitted into 12 x 16 in, centred horizontally, top-aligned)")
    if report.ok and not report.pixels_checked:
        lines.append("VERDICT: the header checks pass, but the pixels were not checked (exit 3). Visible "
                     "content, empty margins and contrast with the shirt are unknown here; the store checks "
                     "the first two at upload, but contrast only after the design fee. Install Pillow and "
                     "check again before paying.")
    elif report.ok:
        lines.append("VERDICT: the store accepts this file."
                     + (" Fix the warnings first if you can." if report.warnings else ""))
    else:
        lines.append("VERDICT: the upload would be refused (nothing is charged). Fix it and check again.")
    for label, items in (
        ("refused at upload", report.refused),
        ("warning", report.warnings),
    ):
        for finding in items:
            lines.append(f"  [{label}] {finding.code}: {finding.message}")
    lines.append(f"  pixel checks: {report.pixel_checks}")
    if report.stats:
        lines.append("  " + ", ".join(f"{k}={v}" for k, v in sorted(report.stats.items())))
    return "\n".join(lines)


def to_json(report: Report) -> str:
    def items(findings: list[Finding]) -> list[dict]:
        return [{"code": f.code, "message": f.message} for f in findings]

    return json.dumps({
        "path": report.path,
        "ok": report.ok,
        "sizeBytes": report.size_bytes,
        "widthPx": report.info.width if report.info else None,
        "heightPx": report.info.height if report.info else None,
        "alphaChannel": report.info.can_be_transparent if report.info else None,
        "effectiveDpi": report.effective_dpi,
        "printInches": list(report.print_inches) if report.print_inches else None,
        "refusedAtUpload": items(report.refused),
        "pixelsChecked": report.pixels_checked,
        "warnings": items(report.warnings),
        "pixelChecks": report.pixel_checks,
        "stats": report.stats,
    }, indent=2)


def main(argv: list[str] | None = None, stdout=None) -> int:
    stdout = stdout or sys.stdout
    parser = argparse.ArgumentParser(description="Check a T-shirt PNG against the store's print rules.")
    parser.add_argument("png", type=Path)
    parser.add_argument("--color", help="shirt color: black, white, or #rrggbb (adds the contrast check)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    parser.add_argument("--no-pixels", action="store_true", help="header checks only")
    args = parser.parse_args(argv)
    if args.color:
        try:
            parse_hex(args.color)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    try:
        report = check(args.png, args.color, pixels=not args.no_pixels)
    except OSError as exc:
        print(f"error: cannot read {args.png}: {exc.strerror or exc}", file=sys.stderr)
        return 2
    except ArtworkDecodeError as exc:
        print(f"error: {args.png}: {exc}. The store refuses a PNG it cannot decode; export it again.",
              file=sys.stderr)
        return 2
    print(to_json(report) if args.json else render(report), file=stdout)
    if not report.ok:
        return 1
    return 0 if report.pixels_checked else 3


if __name__ == "__main__":
    sys.exit(main())
