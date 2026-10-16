"""The design-a-shirt skill: its artwork checker and the guards on its text.

``check_artwork.py`` is tested offline. The header checks run on PNGs built
here with the standard library; the pixel judgement is a pure function fed
numbers, so CI needs nothing but pytest. One end-to-end test runs the Pillow
path when Pillow happens to be installed and skips otherwise.

The text guards hold the parts of the skill that must not drift: every store
route it names is one the store documents (llms-full.txt, "Custom Products"
and "Designed by our customers"), the agent never approves or acknowledges for
the person, every payment is capped, and the custody sentence is present.
"""
import io
import json
import re
import struct
import sys
import zlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / "skills" / "design-a-shirt"
SCRIPTS = SKILL_DIR / "scripts"
SKILL = SKILL_DIR / "SKILL.md"
README = SKILL_DIR / "README.md"
CUSTODY = "Lightning Enable does not hold funds; the payment provider facilitates custody and settlement."

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_artwork  # noqa: E402


def chunk(ctype: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + ctype + body + struct.pack(">I", zlib.crc32(ctype + body) & 0xFFFFFFFF)


def png(width, height, color_type=6, extra=(), idat=None) -> bytes:
    """A structurally valid PNG. The IDAT is a token stream: the checker never decodes pixels."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    chunks = [chunk(b"IHDR", ihdr), *extra, chunk(b"IDAT", idat or zlib.compress(b"\x00")), chunk(b"IEND", b"")]
    return check_artwork.PNG_SIGNATURE + b"".join(chunks)


def run(tmp_path, data: bytes, *flags):
    path = tmp_path / "art.png"
    path.write_bytes(data)
    out = io.StringIO()
    code = check_artwork.main([str(path), "--no-pixels", "--json", *flags], stdout=out)
    return code, json.loads(out.getvalue())


def codes(findings):
    return {f["code"] for f in findings}


# --- header checks -----------------------------------------------------------


def test_a_full_size_rgba_png_is_accepted_at_300_dpi(tmp_path):
    code, report = run(tmp_path, png(3600, 4800))
    assert code == 0 and report["ok"]
    assert report["effectiveDpi"] == 300
    assert report["printInches"] == [12.0, 16.0]
    assert report["alphaChannel"] is True
    assert report["warnings"] == []


def test_the_minimum_square_prints_12_by_12_at_200_dpi(tmp_path):
    _, report = run(tmp_path, png(2400, 2400))
    assert report["effectiveDpi"] == 200
    assert report["printInches"] == [12.0, 12.0]


def test_below_the_minimum_is_refused_at_upload(tmp_path):
    code, report = run(tmp_path, png(2399, 4800))
    assert code == 1
    assert "DimensionsTooSmall" in codes(report["refusedAtUpload"])


def test_over_12000_on_a_side_is_refused(tmp_path):
    _, report = run(tmp_path, png(12001, 2400))
    assert "DimensionsTooLarge" in codes(report["refusedAtUpload"])


def test_12000_square_passes_the_side_limit_but_not_the_pixel_cap(tmp_path):
    _, report = run(tmp_path, png(12000, 12000))
    refused = codes(report["refusedAtUpload"])
    assert "TooManyPixels" in refused and "DimensionsTooLarge" not in refused


def test_low_dpi_warns_below_150():
    # At the 2,400 px minimum every accepted file reaches 200 DPI, so the warning
    # only shows on a file that is also too small (or on a store with a lower minimum).
    assert check_artwork.effective_dpi(2400, 2400)[0] == 200
    assert check_artwork.effective_dpi(1799, 2398)[0] == 149
    report = check_artwork.Report(path="x", size_bytes=1)
    check_artwork.header_findings(report, check_artwork.parse_png(png(1799, 2398)))
    assert "LowEffectiveDpi" in {f.code for f in report.warnings}


def test_an_rgb_png_without_trns_warns_that_the_background_prints(tmp_path):
    code, report = run(tmp_path, png(3600, 4800, color_type=2))
    assert code == 0
    assert report["alphaChannel"] is False
    assert "NoTransparency" in codes(report["warnings"])


def test_a_trns_chunk_counts_as_transparency(tmp_path):
    _, report = run(tmp_path, png(3600, 4800, color_type=2, extra=[chunk(b"tRNS", b"\x00\x00\x00\x00\x00\x00")]))
    assert report["alphaChannel"] is True
    assert "NoTransparency" not in codes(report["warnings"])


def test_animation_and_icc_profiles_are_reported(tmp_path):
    extra = [chunk(b"acTL", b"\x00" * 8), chunk(b"iCCP", b"sRGB\x00\x00" + zlib.compress(b"x"))]
    _, report = run(tmp_path, png(3600, 4800, extra=extra))
    assert {"AnimationDiscarded", "ColorProfileDiscarded"} <= codes(report["warnings"])


def test_a_damaged_png_is_refused(tmp_path):
    data = bytearray(png(3600, 4800))
    data[20] ^= 0xFF  # inside IHDR: the CRC no longer matches
    code, report = run(tmp_path, bytes(data))
    assert code == 1
    assert "NotAReadablePng" in codes(report["refusedAtUpload"])


def test_a_jpeg_is_refused(tmp_path):
    code, report = run(tmp_path, b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    assert code == 1
    assert "NotAReadablePng" in codes(report["refusedAtUpload"])


def test_a_bad_color_is_a_usage_error(tmp_path):
    path = tmp_path / "art.png"
    path.write_bytes(png(3600, 4800))
    assert check_artwork.main([str(path), "--color", "orange"], stdout=io.StringIO()) == 2


def test_the_text_report_states_a_verdict(tmp_path):
    path = tmp_path / "art.png"
    path.write_bytes(png(1000, 1000))
    out = io.StringIO()
    assert check_artwork.main([str(path), "--no-pixels"], stdout=out) == 1
    assert "VERDICT: the upload would be refused" in out.getvalue()


def test_without_pixel_checks_the_verdict_does_not_claim_acceptance(tmp_path):
    # A fully transparent PNG passes every header check; only the pixels catch it.
    path = tmp_path / "art.png"
    path.write_bytes(png(3600, 4800))
    out = io.StringIO()
    assert check_artwork.main([str(path), "--no-pixels"], stdout=out) == 0
    assert "the pixels were not checked" in out.getvalue()
    assert "the store accepts this file" not in out.getvalue()


# --- pixel judgement (pure) --------------------------------------------------


def judged(width, height, histogram, bbox, contrast=None):
    report = check_artwork.Report(path="x", size_bytes=1)
    check_artwork.pixel_findings(report, width, height, histogram, bbox, contrast)
    return report


def histogram(**counts):
    hist = [0] * 256
    for alpha, count in counts.items():
        hist[int(alpha[1:])] = count
    return hist


def test_fully_transparent_fails_after_the_fee():
    report = judged(100, 100, histogram(a0=10_000), None)
    assert not report.ok
    assert [f.code for f in report.fails_after_fee] == ["NoVisibleContent"]


def test_faint_content_below_half_alpha_counts_as_nothing_to_print():
    report = judged(100, 100, histogram(a0=9_000, a127=1_000), (10, 10, 20, 20))
    assert [f.code for f in report.fails_after_fee] == ["NoVisibleContent"]


def test_tight_artwork_on_a_transparent_canvas_is_clean():
    report = judged(100, 100, histogram(a0=2_000, a255=8_000), (5, 5, 95, 95))
    assert report.ok and report.warnings == []
    assert report.stats["empty_margin_fraction"] == pytest.approx(0.19)


def test_more_than_40_percent_empty_margin_warns():
    report = judged(100, 100, histogram(a0=7_000, a255=3_000), (20, 20, 80, 80))
    assert {f.code for f in report.warnings} == {"ExcessiveEmptyMargins"}


def test_exactly_40_percent_does_not_warn():
    # 1 - (100 * 60) / 10000 = 0.40, and the store warns only above it.
    report = judged(100, 100, histogram(a0=4_000, a255=6_000), (0, 0, 100, 60))
    assert report.warnings == []


def test_an_all_opaque_rgba_file_warns_once():
    report = judged(100, 100, histogram(a255=10_000), (0, 0, 100, 100))
    assert [f.code for f in report.warnings] == ["NoTransparency"]


def test_low_contrast_warns_from_half_the_visible_artwork():
    assert "LowContrastWithGarment" in {
        f.code for f in judged(100, 100, histogram(a0=1, a255=9_999), (0, 0, 100, 100), 0.5).warnings
    }
    assert "LowContrastWithGarment" not in {
        f.code for f in judged(100, 100, histogram(a0=1, a255=9_999), (0, 0, 100, 100), 0.49).warnings
    }


def test_contrast_math_matches_wcag():
    black = check_artwork.luminance((0, 0, 0))
    white = check_artwork.luminance((255, 255, 255))
    assert check_artwork.contrast_ratio(black, white) == pytest.approx(21.0)
    assert check_artwork.parse_hex("black") == (0x0C, 0x0C, 0x0C)
    assert check_artwork.parse_hex("#FFFFFF") == (255, 255, 255)


def test_pillow_end_to_end(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")
    good = Image.new("RGBA", (2400, 2400), (0, 0, 0, 0))
    ImageDraw.Draw(good).rectangle((100, 100, 2300, 2300), fill=(247, 147, 26, 255))
    good.save(tmp_path / "good.png")
    Image.new("RGBA", (2400, 2400), (0, 0, 0, 0)).save(tmp_path / "empty.png")

    report = check_artwork.check(tmp_path / "good.png", "black")
    assert report.ok and report.pixel_checks == "done" and report.warnings == []
    report = check_artwork.check(tmp_path / "empty.png", "black")
    assert [f.code for f in report.fails_after_fee] == ["NoVisibleContent"]


def test_the_script_documents_its_exit_codes_and_offline_use():
    doc = check_artwork.__doc__
    assert "makes no network request and never pays" in doc
    assert "Exit status: 0" in doc and "Python 3.10" in doc


# --- text guards -------------------------------------------------------------

# Every store route the skill may name, from llms-full.txt. `{id}` stands for
# any one path segment.
DOCUMENTED_ROUTES = {
    "/api/store/custom",  # the prefix, as prose writes it: `/api/store/custom/*`
    "/api/store/custom/catalog",
    "/api/store/custom/uploads",
    "/api/store/custom/designs",
    "/api/store/custom/designs/{id}",
    "/api/store/custom/designs/{id}/mockups/{id}",
    "/api/store/custom/designs/{id}/quotes",
    "/api/store/custom/designs/{id}/publish",
    "/api/store/custom/designs/{id}/publication",
    "/api/store/custom/designs/{id}/withdraw",
    "/api/store/custom/checkout",
    "/api/store/custom/orders/{id}",
    "/api/store/custom/orders/{id}/fulfill",
    "/api/store/custom/listings",
    "/api/store/custom/listings/{id}",
    "/api/store/custom/listings/{id}/checkout",
    "/api/store/custom/listings/{id}/mockup",
    "/store/custom/design/{id}/approve",
}
ROUTE = re.compile(r"(/(?:api/)?store/custom/[A-Za-z0-9_<>{}./-]*)")
PLACEHOLDER = re.compile(r"^(?:<[^>]*>|\{[^}]*\}|[a-z]{3}_\S*|\.\.\.)$")


def normalize(route: str) -> str:
    route = route.rstrip("./")
    parts = [("{id}" if PLACEHOLDER.match(p) else p) for p in route.split("/")]
    return "/".join(parts)


@pytest.mark.parametrize("path", (SKILL, README), ids=lambda p: p.name)
def test_every_store_route_is_documented(path):
    named = {normalize(m) for m in ROUTE.findall(path.read_text(encoding="utf-8"))}
    unknown = sorted(named - DOCUMENTED_ROUTES)
    assert not unknown, f"{path.name} names store routes llms-full.txt does not document: {unknown}"


def test_the_skill_covers_the_whole_flow():
    named = {normalize(m) for m in ROUTE.findall(SKILL.read_text(encoding="utf-8"))}
    for route in (
        "/api/store/custom/catalog",
        "/api/store/custom/uploads",
        "/api/store/custom/designs",
        "/api/store/custom/designs/{id}",
        "/api/store/custom/designs/{id}/quotes",
        "/api/store/custom/checkout",
        "/api/store/custom/orders/{id}",
        "/api/store/custom/designs/{id}/publish",
        "/api/store/custom/listings/{id}/checkout",
        "/store/custom/design/{id}/approve",
    ):
        assert route in named, route


def flat(path):
    return " ".join(path.read_text(encoding="utf-8").split())


def test_the_agent_never_approves_or_acknowledges_for_the_person():
    text = SKILL.read_text(encoding="utf-8")
    assert "the agent never approves" in text
    assert "Never tick, send or claim an acknowledgement on the person's behalf" in text
    # No request body in the skill sets the manufacture acknowledgements.
    assert not re.search(r'"acknowledgePhysicalVariation"\s*:', text)
    assert "?credential=" in text


@pytest.mark.parametrize("path", (SKILL, README), ids=lambda p: p.name)
def test_custody_sentence(path):
    assert CUSTODY in flat(path)


def test_every_pay_invoice_call_is_capped():
    calls = re.findall(r"pay_invoice\(([^)]*)\)", SKILL.read_text(encoding="utf-8"))
    assert calls
    for args in calls:
        assert "max_sats=" in args, args


def test_the_skill_asks_for_postal_level_destination_only():
    text = flat(SKILL)
    assert "size, state and ZIP code only" in text
    assert "support@lightningenable.com and we may be able to accommodate your order" in text


def test_the_skill_names_every_error_code_the_owner_listed():
    text = SKILL.read_text(encoding="utf-8")
    for code in (
        "custom_products_disabled",
        "upload_expired",
        "payment_pending",
        "payment_superseded",
        "design_closed",
        "design_taken_down",
        "quote_not_payable",
        "listing_not_available",
        "invoice_outlives_quote",
        "publish_limit_reached",
        "mint_rate_limited",
    ):
        assert f"`{code}`" in text or f" {code}`" in text, code


def test_the_store_specs_match_the_catalog():
    text = flat(SKILL)
    for spec in ("2,400 x 2,400 px", "12,000 px on a side", "40 million pixels", "50 MB", "12 x 16 in",
                 "150 DPI", "3,600 x 4,800 fills the area at 300 DPI", "2,400 x 2,400 prints 12 x 12 in at 200 DPI"):
        assert spec in text, spec
    assert check_artwork.MAX_TOTAL_PIXELS == 40_000_000
    assert check_artwork.PRINT_AREA_IN == (12, 16)
