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
        "get_pdf_info"
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


# Note: Full integration tests would require actual PDF files
# These would be added in a real-world scenario with test fixtures
