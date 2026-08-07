"""Tests for PDF Redaction MCP Server."""

import pytest
import json
from pathlib import Path


def test_server_import():
    """Test that the server module can be imported."""
    from pdf_redaction_mcp.server import mcp
    assert mcp is not None
    assert mcp.name == "PDF Redaction Server"


def test_tools_registered():
    """Test that all expected tools are registered."""
    from pdf_redaction_mcp.server import mcp
    
    expected_tools = [
        "load_pdf",
        "save_pdf",
        "close_pdf",
        "list_loaded_pdfs",
        "extract_text_from_pdf",
        "search_text_in_pdf",
        "redact_text_by_search",
        "redact_by_coordinates",
        "redact_images_in_pdf",
        "verify_redactions",
        "get_pdf_info",
        "list_vector_drawings",
        "render_page",
        "list_image_placements"
    ]
    
    # Get all tool definitions from the MCP server
    tool_names = []
    for item in dir(mcp):
        attr = getattr(mcp, item)
        # Check if it's a tool (has a 'name' attribute and is a tool)
        if hasattr(attr, 'name') and hasattr(attr, '__call__'):
            # This is a decorated tool
            continue
    
    # Alternative: check that the functions exist in the server module
    from pdf_redaction_mcp import server
    for expected_tool in expected_tools:
        assert hasattr(server, expected_tool), f"Function {expected_tool} not found in server module"


def test_extract_text_error_handling():
    """Test error handling for non-existent document ID."""
    # Import the actual function, not the decorated version
    from pdf_redaction_mcp import server
    
    # Get the actual function before decoration
    extract_fn = server.extract_text_from_pdf
    if hasattr(extract_fn, 'fn'):
        extract_fn = extract_fn.fn
    
    result = extract_fn(
        document_id="nonexistent_doc",
        format="text"
    )
    
    # Should return error as JSON
    result_dict = json.loads(result)
    assert "error" in result_dict
    assert "not found" in result_dict["error"].lower()


def test_search_text_error_handling():
    """Test error handling for search in non-existent document."""
    from pdf_redaction_mcp import server
    
    # Get the actual function
    search_fn = server.search_text_in_pdf
    if hasattr(search_fn, 'fn'):
        search_fn = search_fn.fn
    
    result = search_fn(
        document_id="nonexistent_doc",
        search_string="test"
    )
    
    # Should return error as JSON
    result_dict = json.loads(result)
    assert "error" in result_dict
    assert "not found" in result_dict["error"].lower()


def test_get_pdf_info_error_handling():
    """Test error handling for PDF info on non-existent document."""
    from pdf_redaction_mcp import server
    
    # Get the actual function
    info_fn = server.get_pdf_info
    if hasattr(info_fn, 'fn'):
        info_fn = info_fn.fn
    
    result = info_fn(document_id="nonexistent_doc")
    
    # Should return error as JSON
    result_dict = json.loads(result)
    assert "error" in result_dict
    assert "not found" in result_dict["error"].lower()


def test_load_pdf_error_handling():
    """Test error handling for loading non-existent PDF file."""
    from pdf_redaction_mcp import server
    
    # Get the actual function
    load_fn = server.load_pdf
    if hasattr(load_fn, 'fn'):
        load_fn = load_fn.fn
    
    result = load_fn(pdf_path="/nonexistent/file.pdf")
    
    # Should return error as JSON
    result_dict = json.loads(result)
    assert "error" in result_dict


def test_list_loaded_pdfs():
    """Test listing loaded PDFs when none are loaded."""
    from pdf_redaction_mcp import server
    
    # Clear any loaded documents first
    server.DOCUMENT_STORE.clear()
    
    # Get the actual function
    list_fn = server.list_loaded_pdfs
    if hasattr(list_fn, 'fn'):
        list_fn = list_fn.fn
    
    result = list_fn()
    
    # Should return valid JSON with empty list
    result_dict = json.loads(result)
    assert "total_documents" in result_dict
    assert result_dict["total_documents"] == 0
    assert "documents" in result_dict
    assert len(result_dict["documents"]) == 0


def _dark_pixel_count(page, clip):
    """Count near-black rendered pixels inside clip."""
    pix = page.get_pixmap(clip=clip)
    return sum(
        1
        for x in range(pix.width)
        for y in range(pix.height)
        if sum(pix.pixel(x, y)[:3]) < 300
    )


def _make_text_and_vector_doc():
    """One page: black text at the top, a filled vector rectangle below it."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((30, 50), "SECRET TABLE", fontsize=18, color=(0, 0, 0))
    page.draw_rect(
        pymupdf.Rect(30, 100, 150, 140), color=(0, 0, 0), fill=(0.5, 0.5, 0.5)
    )
    return doc


def test_region_redaction_leaves_text_visible():
    """remove_text=false must not paint over the text it leaves standing.

    The region pass runs with PDF_REDACT_TEXT_NONE, which deliberately keeps
    overlapping glyphs; a fill would cover them — extractable but invisible.
    """
    import pymupdf
    from pdf_redaction_mcp import server

    redact_fn = server.redact_by_coordinates
    if hasattr(redact_fn, "fn"):
        redact_fn = redact_fn.fn

    doc = _make_text_and_vector_doc()
    server.DOCUMENT_STORE.clear()
    server.DOCUMENT_STORE["region_doc"] = doc

    text_area = pymupdf.Rect(20, 30, 280, 60)
    assert _dark_pixel_count(doc[0], text_area) > 0

    # One rect covering both the text and the vector rectangle, as the
    # pipeline sends it, with the pipeline's white fill_color.
    result = json.loads(redact_fn(
        document_id="region_doc",
        redactions=[
            {"page": 0, "bbox": [20, 30, 280, 150], "remove_text": False}
        ],
        fill_color=(1, 1, 1),
    ))
    assert result["total_redactions"] == 1

    page = doc[0]
    # (a) the text is still extractable
    assert "SECRET TABLE" in page.get_text()
    # (b) and still visibly rendered — no white paint over it
    assert _dark_pixel_count(page, text_area) > 0
    # (c) the covered vector rectangle is gone
    assert page.get_drawings() == []

    server.DOCUMENT_STORE.clear()


def test_text_redaction_still_fills_and_overlays():
    """remove_text=true keeps the fill: cleared white space plus the marker."""
    import pymupdf
    from pdf_redaction_mcp import server

    redact_fn = server.redact_by_coordinates
    if hasattr(redact_fn, "fn"):
        redact_fn = redact_fn.fn

    doc = _make_text_and_vector_doc()
    server.DOCUMENT_STORE.clear()
    server.DOCUMENT_STORE["text_doc"] = doc

    text_area = pymupdf.Rect(20, 30, 280, 60)
    dark_before = _dark_pixel_count(doc[0], text_area)
    assert dark_before > 0

    result = json.loads(redact_fn(
        document_id="text_doc",
        redactions=[
            {
                "page": 0,
                "bbox": [20, 30, 280, 60],
                "remove_text": True,
                "text": "[REDACTED]",
            }
        ],
        fill_color=(1, 1, 1),
    ))
    assert result["total_redactions"] == 1

    page = doc[0]
    extracted = page.get_text()
    assert "SECRET TABLE" not in extracted
    assert "[REDACTED]" in extracted
    # The glyphs are gone and the rect is white-filled: far fewer dark pixels,
    # the remainder being the overlay marker's own glyphs.
    dark_after = _dark_pixel_count(page, text_area)
    assert 0 < dark_after < dark_before
    # The vector rectangle outside the redaction is untouched by the text pass
    # (the white fill itself also shows up as a drawing)
    assert any(
        pymupdf.Rect(30, 100, 150, 140) in [item[1] for item in d["items"]]
        for d in page.get_drawings()
    )

    server.DOCUMENT_STORE.clear()


def _redact_fn():
    from pdf_redaction_mcp import server

    fn = server.redact_by_coordinates
    return fn.fn if hasattr(fn, "fn") else fn


def _ink_paths(page):
    """Stroked, curve-heavy paths — the signature, not the rules."""
    return [
        d for d in page.get_drawings()
        if d["type"] == "s" and len(d["items"]) > 5
    ]


def test_region_redaction_leaves_ink_standing():
    """The bug remove_line_art exists for, pinned so it cannot come back silently.

    A region redaction removes only vector art it counts as *covered*, and that test
    does not fire on a long run of bezier curves. The paint lands and the path
    survives underneath: visually gone, recoverable in full from the content stream.
    Measured on a real signature, a rectangle enclosing the whole of the path's
    reported bounding box still left it in place.
    """
    from pdf_redaction_mcp import server

    doc = _make_signature_doc()
    server.DOCUMENT_STORE.clear()
    server.DOCUMENT_STORE["sig_doc"] = doc

    assert len(_ink_paths(doc[0])) == 1

    # Generous: wider and taller than the ink on every side.
    result = json.loads(_redact_fn()(
        document_id="sig_doc",
        redactions=[{"page": 0, "bbox": [80, 100, 240, 195], "remove_text": False}],
    ))
    assert result["total_redactions"] == 1

    assert len(_ink_paths(doc[0])) == 1, "region redaction unexpectedly removed the ink"

    server.DOCUMENT_STORE.clear()


def test_remove_line_art_removes_the_ink():
    """remove_line_art is what actually takes a signature out of the content stream."""
    from pdf_redaction_mcp import server

    doc = _make_signature_doc()
    server.DOCUMENT_STORE.clear()
    server.DOCUMENT_STORE["sig_doc"] = doc

    assert len(_ink_paths(doc[0])) == 1

    result = json.loads(_redact_fn()(
        document_id="sig_doc",
        redactions=[{
            "page": 0,
            "bbox": [95, 105, 220, 185],
            "remove_text": False,
            "remove_line_art": True,
        }],
    ))
    assert result["total_redactions"] == 1
    assert result["redactions"][0]["remove_line_art"] is True

    assert _ink_paths(doc[0]) == [], "the signature is still in the content stream"

    server.DOCUMENT_STORE.clear()


def test_remove_line_art_is_refused_with_remove_text():
    """The text pass preserves vector art by design; the pair describes no pass."""
    from pdf_redaction_mcp import server

    doc = _make_signature_doc()
    server.DOCUMENT_STORE.clear()
    server.DOCUMENT_STORE["sig_doc"] = doc

    result = json.loads(_redact_fn()(
        document_id="sig_doc",
        redactions=[{
            "page": 0,
            "bbox": [95, 105, 220, 185],
            "remove_text": True,
            "remove_line_art": True,
        }],
    ))

    assert result["total_redactions"] == 0
    assert result["redactions"][0]["status"] == "error"
    assert "remove_text=false" in result["redactions"][0]["message"]
    assert len(_ink_paths(doc[0])) == 1

    server.DOCUMENT_STORE.clear()


def test_remove_line_art_spares_art_it_does_not_touch():
    """Destructive in proportion to the rectangle, and no further.

    IF_TOUCHED takes everything the rectangle clips, which is the cost of reaching
    the ink. What it must not do is reach past its own bounds.
    """
    from pdf_redaction_mcp import server

    doc = _make_signature_doc()
    server.DOCUMENT_STORE.clear()
    server.DOCUMENT_STORE["sig_doc"] = doc

    # The rule sits at y=60; the ink runs from y~110 down. This clears only the ink.
    _redact_fn()(
        document_id="sig_doc",
        redactions=[{
            "page": 0,
            "bbox": [95, 105, 220, 185],
            "remove_text": False,
            "remove_line_art": True,
        }],
    )

    survivors = doc[0].get_drawings()
    assert _ink_paths(doc[0]) == []
    # The rule is untouched: some path still spans the page at its height.
    assert any(
        d["rect"].y0 < 65 and d["rect"].width > 200 for d in survivors
    ), "the rule outside the rectangle was destroyed"

    server.DOCUMENT_STORE.clear()


def _drawings_fn():
    from pdf_redaction_mcp import server

    fn = server.list_vector_drawings
    return fn.fn if hasattr(fn, "fn") else fn


def test_list_vector_drawings_error_handling():
    """Test error handling for drawings on a non-existent document."""
    result = json.loads(_drawings_fn()(document_id="nonexistent_doc"))

    assert "error" in result
    assert "not found" in result["error"].lower()


def _make_signature_doc():
    """One page: a hairline rule, and a stroked squiggle standing in for ink.

    Many bezier segments whose control points sit well outside the curve they
    draw, because that is both what handwriting looks like and the property that
    makes a region redaction's "covered" test miss it.
    """
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=300, height=200)

    # A table rule: long, no height, one segment. The kind of path that is noise.
    page.draw_line(pymupdf.Point(20, 60), pymupdf.Point(280, 60), width=0.5)

    shape = page.new_shape()
    x, baseline, reach = 100.0, 150.0, 55.0
    for segment in range(8):
        next_x = x + 14.5
        offset = -reach if segment % 2 == 0 else reach
        shape.draw_bezier(
            pymupdf.Point(x, baseline),
            pymupdf.Point(x + 4, baseline + offset),
            pymupdf.Point(next_x - 4, baseline + offset),
            pymupdf.Point(next_x, baseline),
        )
        x = next_x
    shape.finish(color=(0, 0, 0), width=1.5)
    shape.commit()

    return doc


def test_list_vector_drawings_finds_a_stroked_signature():
    """The signature case: ink that carries no text and is not an image.

    This is what search_text_in_pdf and redact_images_in_pdf both miss, and the
    reason this tool exists — the bbox it returns is what redact_by_coordinates
    needs to clear the signature.
    """
    from pdf_redaction_mcp import server

    doc = _make_signature_doc()
    server.DOCUMENT_STORE.clear()
    server.DOCUMENT_STORE["sig_doc"] = doc

    # Neither of the other locators can see it.
    assert doc[0].get_text().strip() == ""
    assert len(doc[0].get_images()) == 0

    everything = json.loads(_drawings_fn()(document_id="sig_doc"))
    assert everything["total_paths"] >= 2

    # Filtering on height alone separates the signature from the rule.
    filtered = json.loads(_drawings_fn()(document_id="sig_doc", min_height=10.0))
    assert filtered["matched_filter"] == 1

    signature = filtered["drawings"][0]
    assert signature["page"] == 0
    assert signature["type"] == "s"
    assert signature["item_kinds"].get("c", 0) >= 2

    # The bbox covers the drawn stroke, which is what a redaction is aimed at.
    x0, y0, x1, y1 = signature["bbox"]
    assert x0 <= 100 and x1 >= 215
    assert y1 > y0 + 10

    server.DOCUMENT_STORE.clear()


def test_list_vector_drawings_reports_what_it_dropped():
    """A truncated answer must never read as the whole page."""
    from pdf_redaction_mcp import server

    doc = _make_signature_doc()
    server.DOCUMENT_STORE.clear()
    server.DOCUMENT_STORE["sig_doc"] = doc

    result = json.loads(_drawings_fn()(document_id="sig_doc", limit=1))

    assert result["returned"] == 1
    assert result["omitted_by_limit"] == result["matched_filter"] - 1
    assert result["total_paths"] >= result["matched_filter"]

    server.DOCUMENT_STORE.clear()


def test_list_vector_drawings_omits_path_points():
    """The point coordinates are the drawing; a bbox is enough to redact it."""
    from pdf_redaction_mcp import server

    doc = _make_signature_doc()
    server.DOCUMENT_STORE.clear()
    server.DOCUMENT_STORE["sig_doc"] = doc

    result = json.loads(_drawings_fn()(document_id="sig_doc"))

    for drawing in result["drawings"]:
        assert "items" not in drawing
        assert "item_count" in drawing

    server.DOCUMENT_STORE.clear()


def _render_fn():
    from pdf_redaction_mcp import server

    fn = server.render_page
    return fn.fn if hasattr(fn, "fn") else fn


def _placements_fn():
    from pdf_redaction_mcp import server

    fn = server.list_image_placements
    return fn.fn if hasattr(fn, "fn") else fn


def _make_picture_doc():
    """One page: text at the top, a placed raster image lower down.

    The picture stands in for a scan or screenshot holding a value — content
    that answers to neither text search nor vector listing, which is the case
    render_page and list_image_placements exist for.
    """
    import pymupdf

    image_doc = pymupdf.open()
    image_page = image_doc.new_page(width=100, height=60)
    image_page.draw_rect(
        pymupdf.Rect(0, 0, 100, 60), color=(0, 0, 0), fill=(0.2, 0.4, 0.8)
    )
    png = image_page.get_pixmap().tobytes("png")
    image_doc.close()

    doc = pymupdf.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((30, 40), "COVER LETTER", fontsize=14, color=(0, 0, 0))
    page.insert_image(
        pymupdf.Rect(50, 80, 250, 180), stream=png, keep_proportion=False
    )
    return doc


def test_render_page_error_handling():
    """Missing documents and out-of-range pages answer as JSON errors."""
    from pdf_redaction_mcp import server

    result = json.loads(_render_fn()(document_id="nonexistent_doc", page_number=0))
    assert "error" in result
    assert "not found" in result["error"].lower()

    server.DOCUMENT_STORE.clear()
    server.DOCUMENT_STORE["pic_doc"] = _make_picture_doc()

    result = json.loads(_render_fn()(document_id="pic_doc", page_number=5))
    assert "error" in result
    assert "invalid page" in result["error"].lower()

    server.DOCUMENT_STORE.clear()


def test_render_page_returns_metadata_and_png():
    """Two blocks: the pixel-to-point mapping, then a PNG that reopens."""
    import pymupdf
    from pdf_redaction_mcp import server

    server.DOCUMENT_STORE.clear()
    server.DOCUMENT_STORE["pic_doc"] = _make_picture_doc()

    blocks = _render_fn()(document_id="pic_doc", page_number=0, dpi=144)
    assert len(blocks) == 2

    metadata = json.loads(blocks[0])
    assert metadata["page"] == 0
    assert metadata["page_width_pt"] == 300
    assert metadata["scale"] == pytest.approx(2.0)
    assert metadata["image_width_px"] == 600

    rendered = pymupdf.Pixmap(blocks[1].data)
    assert (rendered.width, rendered.height) == (600, 400)

    server.DOCUMENT_STORE.clear()


def test_render_page_caps_oversized_renders():
    """A poster-sized page cannot produce an image too large to look at."""
    import pymupdf
    from pdf_redaction_mcp import server

    doc = pymupdf.open()
    doc.new_page(width=2000, height=1000)
    server.DOCUMENT_STORE.clear()
    server.DOCUMENT_STORE["poster"] = doc

    blocks = _render_fn()(document_id="poster", page_number=0, dpi=300)
    metadata = json.loads(blocks[0])

    assert metadata["image_width_px"] <= server.RENDER_MAX_SIDE_PX
    # The reported scale must describe the capped render, not the request.
    assert metadata["scale"] == pytest.approx(
        metadata["image_width_px"] / metadata["page_width_pt"], rel=0.01
    )

    server.DOCUMENT_STORE.clear()


def test_list_image_placements_error_handling():
    """Test error handling for placements on a non-existent document."""
    result = json.loads(_placements_fn()(document_id="nonexistent_doc"))

    assert "error" in result
    assert "not found" in result["error"].lower()


def test_list_image_placements_sites_the_picture():
    """The placement bbox is the rectangle a whole-image redaction needs."""
    from pdf_redaction_mcp import server

    doc = _make_picture_doc()
    server.DOCUMENT_STORE.clear()
    server.DOCUMENT_STORE["pic_doc"] = doc

    # Text search cannot see into the picture; this is the tool that can say
    # where it sits.
    result = json.loads(_placements_fn()(document_id="pic_doc"))

    assert result["total_placements"] == 1
    placement = result["placements"][0]
    assert placement["page"] == 0

    x0, y0, x1, y1 = placement["bbox"]
    assert (x0, y0, x1, y1) == pytest.approx((50, 80, 250, 180), abs=1)
    assert placement["source_width_px"] == 100
    assert "pixels" not in placement

    server.DOCUMENT_STORE.clear()


def test_list_image_placements_reports_what_it_dropped():
    """A truncated or filtered answer must never read as the whole page."""
    from pdf_redaction_mcp import server

    doc = _make_picture_doc()
    server.DOCUMENT_STORE.clear()
    server.DOCUMENT_STORE["pic_doc"] = doc

    filtered = json.loads(
        _placements_fn()(document_id="pic_doc", min_width=500.0)
    )
    assert filtered["total_placements"] == 1
    assert filtered["matched_filter"] == 0
    assert filtered["placements"] == []

    server.DOCUMENT_STORE.clear()


# Note: Full integration tests would require actual PDF files
# These would be added in a real-world scenario with test fixtures
