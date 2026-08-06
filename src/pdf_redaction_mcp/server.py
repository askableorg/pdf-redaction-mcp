"""PDF Redaction MCP Server using FastMCP and pymupdf.

This MCP server provides tools for:
- Converting PDFs to text
- Searching for text patterns in PDFs
- Redacting text by search string or coordinates
- Redacting images
- Verifying redactions
"""

import sys
import warnings
import pymupdf
import re
import json
import uvicorn
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from fastmcp import FastMCP
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware import Middleware


# Suppress known pymupdf SWIG deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module=".*", message=".*swigvarlink.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module=".*", message=".*SwigPyPacked.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module=".*", message=".*SwigPyObject.*")

# Create the MCP server instance
mcp = FastMCP("PDF Redaction Server")

# Global configuration for PDF base directory
PDF_BASE_DIR: Optional[Path] = None

# In-memory document store for session-based operations
# Maps document_id -> pymupdf.Document
DOCUMENT_STORE: Dict[str, pymupdf.Document] = {}


def add_redact_annot_no_box(
    page: "pymupdf.Page",
    rect,
    text: Optional[str] = None,
    fill: Optional[Tuple[float, float, float]] = None,
    text_color: Optional[Tuple[float, float, float]] = None,
) -> "pymupdf.Annot":
    """Add a redaction annotation without the visible box preview.

    pymupdf's add_redact_annot leaves the annotation with an appearance stream
    drawn by MuPDF — a red rectangle outline — and adds cross-out diagonals on
    top. That preview only matters while the redaction is pending, but it shows
    up if the document is rendered or saved before apply_redactions. Applied
    redactions render from the /IC (fill) and /OverlayText entries, not from
    this preview, so blanking it does not change the redacted output.
    """
    annot = page.add_redact_annot(
        rect, text=text, fill=fill, text_color=text_color, cross_out=False
    )
    try:
        annot._setAP(b" ", 0)
    except Exception:
        # _setAP is a private pymupdf API; if it ever disappears the redaction
        # still works, only the pending-state preview box comes back.
        pass
    return annot


def resolve_pdf_path(pdf_path: str) -> str:
    """Resolve PDF path using the configured base directory if path is relative.
    
    Args:
        pdf_path: Path to PDF file (absolute or relative)
        
    Returns:
        Resolved absolute path
    """
    path = Path(pdf_path)
    if PDF_BASE_DIR and not path.is_absolute():
        return str(PDF_BASE_DIR / path)
    return pdf_path


@mcp.tool()
def load_pdf(pdf_path: str, document_id: Optional[str] = None) -> str:
    """Load a PDF file into memory for session-based operations.
    
    All other PDF tools in the MCP server require a document to be loaded first using this tool.
    The document remains in memory until saved or the session ends.
    
    Args:
        pdf_path: Path to the PDF file to load
        document_id: Optional identifier for this document. If None, uses the filename
    
    Returns:
        JSON string with document_id and basic info about the loaded PDF
    """
    try:
        pdf_path = resolve_pdf_path(pdf_path)
        doc = pymupdf.open(pdf_path)
        
        # Generate document_id if not provided
        if document_id is None:
            document_id = Path(pdf_path).stem
        
        # Close existing document with same ID if it exists
        if document_id in DOCUMENT_STORE:
            DOCUMENT_STORE[document_id].close()
        
        DOCUMENT_STORE[document_id] = doc
        
        result = {
            "document_id": document_id,
            "source_path": pdf_path,
            "pages": len(doc),
            "is_encrypted": doc.is_encrypted,
            "status": "loaded"
        }
        
        return json.dumps(result, indent=2)
    
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "document_id": document_id
        })


@mcp.tool()
def save_pdf(document_id: str, output_path: str) -> str:
    """Save an in-memory PDF document to disk.
    
    The document remains loaded in memory after saving and can continue to be modified.
    
    Args:
        document_id: Identifier of the loaded document
        output_path: Path where the PDF will be saved
    
    Returns:
        JSON string with save confirmation
    """
    try:
        if document_id not in DOCUMENT_STORE:
            return json.dumps({
                "error": f"Document '{document_id}' not found. Use load_pdf first.",
                "available_documents": list(DOCUMENT_STORE.keys())
            })
        
        output_path = resolve_pdf_path(output_path)
        doc = DOCUMENT_STORE[document_id]
        doc.save(output_path)
        
        result = {
            "document_id": document_id,
            "output_path": output_path,
            "pages": len(doc),
            "status": "saved"
        }
        
        return json.dumps(result, indent=2)
    
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "document_id": document_id
        })


@mcp.tool()
def close_pdf(document_id: str) -> str:
    """Close and remove an in-memory PDF document.
    
    Use this to free up memory when you're done with a document.
    Any unsaved changes will be lost.
    
    Args:
        document_id: Identifier of the loaded document
    
    Returns:
        JSON string with close confirmation
    """
    try:
        if document_id not in DOCUMENT_STORE:
            return json.dumps({
                "error": f"Document '{document_id}' not found.",
                "available_documents": list(DOCUMENT_STORE.keys())
            })
        
        DOCUMENT_STORE[document_id].close()
        del DOCUMENT_STORE[document_id]
        
        result = {
            "document_id": document_id,
            "status": "closed"
        }
        
        return json.dumps(result, indent=2)
    
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "document_id": document_id
        })


@mcp.tool()
def list_loaded_pdfs() -> str:
    """List all currently loaded PDF documents in memory.
    
    Returns:
        JSON string with information about all loaded documents
    """
    try:
        documents = []
        for doc_id, doc in DOCUMENT_STORE.items():
            documents.append({
                "document_id": doc_id,
                "pages": len(doc),
                "is_encrypted": doc.is_encrypted,
                "metadata": doc.metadata
            })
        
        result = {
            "total_documents": len(documents),
            "documents": documents
        }
        
        return json.dumps(result, indent=2)
    
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def extract_text_from_pdf(
    document_id: str,
    page_number: Optional[int] = None,
    format: str = "text"
) -> str:
    """Extract text from a loaded PDF document.
    
    The document must be loaded first using load_pdf.
    
    Args:
        document_id: Identifier of the loaded document
        page_number: Specific page number to extract (0-indexed). If None, extracts all pages
        format: Output format - "text" (plain text), "json" (structured), or "blocks" (text blocks)
    
    Returns:
        Extracted text content in the specified format
    """
    try:
        if document_id not in DOCUMENT_STORE:
            return json.dumps({
                "error": f"Document '{document_id}' not found. Use load_pdf first.",
                "available_documents": list(DOCUMENT_STORE.keys())
            })
        
        doc = DOCUMENT_STORE[document_id]
        
        if page_number is not None:
            if page_number < 0 or page_number >= len(doc):
                return json.dumps({"error": f"Invalid page number. PDF has {len(doc)} pages"})
            pages_to_process = [page_number]
        else:
            pages_to_process = range(len(doc))
        
        if format == "json":
            result = {
                "total_pages": len(doc),
                "pages": []
            }
            
            for page_num in pages_to_process:
                page = doc[page_num]
                result["pages"].append({
                    "page_number": page_num,
                    "text": page.get_text("text"),
                    "word_count": len(page.get_text("text").split())
                })
            
            return json.dumps(result, indent=2)
        
        elif format == "blocks":
            result = {
                "total_pages": len(doc),
                "pages": []
            }
            
            for page_num in pages_to_process:
                page = doc[page_num]
                blocks = page.get_text("dict")["blocks"]
                result["pages"].append({
                    "page_number": page_num,
                    "blocks": blocks
                })
            
            return json.dumps(result, indent=2)
        
        else:  # plain text
            text_parts = []
            for page_num in pages_to_process:
                page = doc[page_num]
                text_parts.append(f"=== Page {page_num + 1} ===\n{page.get_text('text')}\n")
            
            return "\n".join(text_parts)
    
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def search_text_in_pdf(
    document_id: str,
    search_string: str,
    case_sensitive: bool = False,
    use_regex: bool = False,
    page_number: Optional[int] = None
) -> str:
    """Search for text in a loaded PDF document and return all occurrences with their locations.
    
    The document must be loaded first using load_pdf.
    
    Args:
        document_id: Identifier of the loaded document
        search_string: Text or regex pattern to search for
        case_sensitive: Whether search should be case sensitive
        use_regex: Whether to treat search_string as a regex pattern
        page_number: Specific page to search (0-indexed). If None, searches all pages
    
    Returns:
        JSON string containing all matches with page numbers and bounding boxes
    """
    try:
        if document_id not in DOCUMENT_STORE:
            return json.dumps({
                "error": f"Document '{document_id}' not found. Use load_pdf first.",
                "available_documents": list(DOCUMENT_STORE.keys())
            })
        
        doc = DOCUMENT_STORE[document_id]
        matches = []
        
        pages_to_search = [page_number] if page_number is not None else range(len(doc))
        
        for page_num in pages_to_search:
            page = doc[page_num]
            
            if use_regex:
                # Extract text and search with regex
                text = page.get_text("text")
                flags = 0 if case_sensitive else re.IGNORECASE
                regex_matches = re.finditer(search_string, text, flags)
                
                for match in regex_matches:
                    # Find the bounding box for this text
                    rects = page.search_for(match.group())
                    for rect in rects:
                        matches.append({
                            "page": page_num,
                            "text": match.group(),
                            "bbox": list(rect),
                            "match_type": "regex"
                        })
            else:
                # Use pymupdf's built-in search
                flags = 0
                if not case_sensitive:
                    flags |= pymupdf.TEXT_PRESERVE_WHITESPACE
                
                rects = page.search_for(search_string)
                for rect in rects:
                    matches.append({
                        "page": page_num,
                        "text": search_string,
                        "bbox": list(rect),
                        "match_type": "exact"
                    })
        
        result = {
            "search_string": search_string,
            "total_matches": len(matches),
            "matches": matches
        }
        
        return json.dumps(result, indent=2)
    
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def redact_text_by_search(
    document_id: str,
    search_strings: List[str],
    fill_color: Tuple[float, float, float] = (0, 0, 0),
    overlay_text: str = "",
    text_color: Tuple[float, float, float] = (1, 1, 1)
) -> str:
    """Redact all occurrences of specified text strings in a loaded PDF document.
    
    The document must be loaded first using load_pdf. Modifications are made in-memory.
    Use save_pdf to write the changes to disk.
    
    Args:
        document_id: Identifier of the loaded document
        search_strings: List of strings to search for and redact
        fill_color: RGB color for redaction box (0-1 range). Default is black (0,0,0)
        overlay_text: Optional text to display over redacted area, use this to explain what has been redacted here
        text_color: RGB color for overlay text (0-1 range). Default is white (1,1,1)
    
    Returns:
        JSON string with summary of redactions applied
    """
    try:
        if document_id not in DOCUMENT_STORE:
            return json.dumps({
                "error": f"Document '{document_id}' not found. Use load_pdf first.",
                "available_documents": list(DOCUMENT_STORE.keys())
            })
        
        doc = DOCUMENT_STORE[document_id]
        total_redactions = 0
        redaction_summary = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_redactions = 0
            
            for search_string in search_strings:
                # Search for all occurrences
                rects = page.search_for(search_string)
                
                for rect in rects:
                    # Add redaction annotation
                    add_redact_annot_no_box(
                        page,
                        rect,
                        text=overlay_text,
                        fill=fill_color,
                        text_color=text_color
                    )
                    page_redactions += 1
                    total_redactions += 1
            
            if page_redactions > 0:
                # Apply all redactions on this page
                page.apply_redactions()
                redaction_summary.append({
                    "page": page_num,
                    "redactions": page_redactions
                })
        
        result = {
            "document_id": document_id,
            "total_redactions": total_redactions,
            "pages_modified": len(redaction_summary),
            "summary": redaction_summary,
            "search_strings": search_strings
        }
        
        return json.dumps(result, indent=2)
    
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def redact_by_coordinates(
    document_id: str,
    redactions: List[Dict[str, Any]],
    fill_color: Tuple[float, float, float] = (0, 0, 0),
    overlay_text: str = ""
) -> str:
    """Redact specific areas of a loaded PDF document by coordinates.
    
    The document must be loaded first using load_pdf. Modifications are made in-memory.
    Use save_pdf to write the changes to disk.
    
    Args:
        document_id: Identifier of the loaded document
        redactions: List of redaction areas, each with:
            - page: Page number (0-indexed)
            - bbox: Bounding box as [x0, y0, x1, y1]
            - text: Optional overlay text for this specific redaction
            - remove_text: Optional bool, default True. True is a text redaction: the
              text under the rectangle is removed, while images and vector art under
              it are left alone. False is a region redaction: the covered area of an
              image is cleared and covered vector art is removed, while every glyph
              the rectangle overlaps is left standing — the rectangle is about the
              page's pixels, and the text it happens to cross belongs to no removal.
        fill_color: RGB color for redaction box (0-1 range). Default is black (0,0,0)
        overlay_text: Default text to display over redacted areas (can be overridden per redaction)

    Returns:
        JSON string with summary of redactions applied
    """
    try:
        if document_id not in DOCUMENT_STORE:
            return json.dumps({
                "error": f"Document '{document_id}' not found. Use load_pdf first.",
                "available_documents": list(DOCUMENT_STORE.keys())
            })
        
        doc = DOCUMENT_STORE[document_id]
        applied_redactions = []

        # Pending annotations per page, split by remove_text. The two kinds are
        # applied in separate passes with different modes, and apply_redactions
        # consumes every annotation pending on the page, so they cannot be added
        # to the page together.
        pending: Dict[int, Dict[bool, List[Tuple[Any, Optional[str]]]]] = {}

        for redaction in redactions:
            page_num = redaction.get("page", 0)
            bbox = redaction.get("bbox")
            redact_text = redaction.get("text", overlay_text)
            remove_text = redaction.get("remove_text", True)

            if page_num < 0 or page_num >= len(doc):
                applied_redactions.append({
                    "status": "error",
                    "message": f"Invalid page number {page_num}"
                })
                continue
            
            if not bbox or len(bbox) != 4:
                applied_redactions.append({
                    "status": "error",
                    "message": "Invalid bbox format. Expected [x0, y0, x1, y1]"
                })
                continue

            # Not coerced: a truthy non-boolean would silently make a region
            # redaction delete text it is only crossing.
            if not isinstance(remove_text, bool):
                applied_redactions.append({
                    "status": "error",
                    "message": "Invalid remove_text. Expected true or false"
                })
                continue

            per_page = pending.setdefault(page_num, {True: [], False: []})
            per_page[remove_text].append((pymupdf.Rect(bbox), redact_text))

            applied_redactions.append({
                "page": page_num,
                "bbox": bbox,
                "remove_text": remove_text,
                "status": "applied"
            })

        # Apply all redactions, one pass per kind on each affected page
        for page_num in sorted(pending):
            page = doc[page_num]

            text_pending = pending[page_num][True]
            if text_pending:
                for rect, redact_text in text_pending:
                    add_redact_annot_no_box(
                        page,
                        rect,
                        text=redact_text,
                        fill=fill_color
                    )
                # The glyphs under the rectangle go. The page's pictures and line
                # art are not what a text redaction was asked to take out, so they
                # are left exactly as they were.
                page.apply_redactions(
                    text=pymupdf.PDF_REDACT_TEXT_REMOVE,
                    images=pymupdf.PDF_REDACT_IMAGE_NONE,
                    graphics=pymupdf.PDF_REDACT_LINE_ART_NONE
                )

            region_pending = pending[page_num][False]
            if region_pending:
                for rect, redact_text in region_pending:
                    add_redact_annot_no_box(
                        page,
                        rect,
                        text=redact_text,
                        fill=fill_color
                    )
                # Pixels go and glyphs stay. IMAGE_PIXELS rewrites the picture with
                # the covered area cleared rather than dropping the whole picture,
                # LINE_ART_REMOVE_IF_COVERED catches art that is not an image at
                # all, and TEXT_NONE leaves the text the rectangle merely overlaps,
                # which no redaction here asked about.
                page.apply_redactions(
                    text=pymupdf.PDF_REDACT_TEXT_NONE,
                    images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                    graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED
                )

        result = {
            "document_id": document_id,
            "total_redactions": len([r for r in applied_redactions if r.get("status") == "applied"]),
            "redactions": applied_redactions
        }
        
        return json.dumps(result, indent=2)
    
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def redact_images_in_pdf(
    document_id: str,
    page_numbers: Optional[List[int]] = None,
    fill_color: Tuple[float, float, float] = (0, 0, 0),
    overlay_text: str = "[IMAGE REDACTED]"
) -> str:
    """Redact all images in specified pages of a loaded PDF document.
    
    The document must be loaded first using load_pdf. Modifications are made in-memory.
    Use save_pdf to write the changes to disk.
    
    Args:
        document_id: Identifier of the loaded document
        page_numbers: List of page numbers to process (0-indexed). If None, processes all pages
        fill_color: RGB color for redaction box (0-1 range). Default is black (0,0,0)
        overlay_text: Text to display over redacted images
    
    Returns:
        JSON string with summary of image redactions
    """
    try:
        if document_id not in DOCUMENT_STORE:
            return json.dumps({
                "error": f"Document '{document_id}' not found. Use load_pdf first.",
                "available_documents": list(DOCUMENT_STORE.keys())
            })
        
        doc = DOCUMENT_STORE[document_id]
        total_images_redacted = 0
        summary = []
        
        pages_to_process = page_numbers if page_numbers is not None else list(range(len(doc)))
        
        for page_num in pages_to_process:
            if page_num < 0 or page_num >= len(doc):
                continue
                
            page = doc[page_num]
            images = page.get_images()
            page_images = 0
            
            for img_index, img in enumerate(images):
                # Get image bounding box
                bbox = page.get_image_bbox(img[7])  # img[7] is the image name/xref
                
                if bbox.is_infinite:
                    continue
                
                # Add redaction annotation
                add_redact_annot_no_box(
                    page,
                    bbox,
                    text=overlay_text,
                    fill=fill_color,
                    text_color=(1, 1, 1)
                )
                page_images += 1
                total_images_redacted += 1
            
            if page_images > 0:
                # Apply redactions with image removal
                page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE)
                summary.append({
                    "page": page_num,
                    "images_redacted": page_images
                })
        
        result = {
            "document_id": document_id,
            "total_images_redacted": total_images_redacted,
            "pages_processed": len(summary),
            "summary": summary
        }
        
        return json.dumps(result, indent=2)
    
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def verify_redactions(
    original_document_id: str,
    redacted_document_id: str,
    search_strings: Optional[List[str]] = None
) -> str:
    """Verify that redactions were applied correctly by comparing two loaded PDF documents.
    
    Both documents must be loaded first using load_pdf.
    
    Args:
        original_document_id: Identifier of the original document
        redacted_document_id: Identifier of the redacted document
        search_strings: Optional list of strings that should no longer appear in redacted PDF
    
    Returns:
        JSON string with verification results
    """
    try:
        if original_document_id not in DOCUMENT_STORE:
            return json.dumps({
                "error": f"Original document '{original_document_id}' not found. Use load_pdf first.",
                "available_documents": list(DOCUMENT_STORE.keys())
            })
        
        if redacted_document_id not in DOCUMENT_STORE:
            return json.dumps({
                "error": f"Redacted document '{redacted_document_id}' not found. Use load_pdf first.",
                "available_documents": list(DOCUMENT_STORE.keys())
            })
        
        orig_doc = DOCUMENT_STORE[original_document_id]
        redact_doc = DOCUMENT_STORE[redacted_document_id]
        
        verification = {
            "original_pages": len(orig_doc),
            "redacted_pages": len(redact_doc),
            "pages_match": len(orig_doc) == len(redact_doc),
            "string_checks": [],
            "text_comparison": []
        }
        
        # Check if specified strings still exist
        if search_strings:
            for search_str in search_strings:
                found_in_redacted = False
                pages_found = []
                
                for page_num in range(len(redact_doc)):
                    page = redact_doc[page_num]
                    rects = page.search_for(search_str)
                    if rects:
                        found_in_redacted = True
                        pages_found.append(page_num)
                
                verification["string_checks"].append({
                    "search_string": search_str,
                    "found_in_redacted": found_in_redacted,
                    "pages_found": pages_found,
                    "status": "FAIL" if found_in_redacted else "PASS"
                })
        
        # Compare text content page by page
        for page_num in range(min(len(orig_doc), len(redact_doc))):
            orig_text = orig_doc[page_num].get_text("text")
            redact_text = redact_doc[page_num].get_text("text")
            
            orig_words = len(orig_text.split())
            redact_words = len(redact_text.split())
            
            verification["text_comparison"].append({
                "page": page_num,
                "original_word_count": orig_words,
                "redacted_word_count": redact_words,
                "words_removed": orig_words - redact_words,
                "text_modified": orig_text != redact_text
            })
        
        # Overall verdict
        all_checks_passed = all(
            check["status"] == "PASS" 
            for check in verification["string_checks"]
        )
        
        verification["overall_verdict"] = {
            "status": "PASS" if all_checks_passed else "FAIL",
            "message": "All redactions verified successfully" if all_checks_passed 
                      else "Some redactions may have failed"
        }
        
        return json.dumps(verification, indent=2)
    
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_pdf_info(document_id: str) -> str:
    """Get basic information about a loaded PDF document.
    
    The document must be loaded first using load_pdf.
    
    Args:
        document_id: Identifier of the loaded document
    
    Returns:
        JSON string with PDF metadata and structure information
    """
    try:
        if document_id not in DOCUMENT_STORE:
            return json.dumps({
                "error": f"Document '{document_id}' not found. Use load_pdf first.",
                "available_documents": list(DOCUMENT_STORE.keys())
            })
        
        doc = DOCUMENT_STORE[document_id]
        
        info = {
            "document_id": document_id,
            "pages": len(doc),
            "metadata": doc.metadata,
            "is_encrypted": doc.is_encrypted,
            "page_info": []
        }
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_info = {
                "page_number": page_num,
                "width": page.rect.width,
                "height": page.rect.height,
                "rotation": page.rotation,
                "image_count": len(page.get_images()),
                "link_count": len(list(page.get_links())),
            }
            info["page_info"].append(page_info)
        
        return json.dumps(info, indent=2)
    
    except Exception as e:
        return json.dumps({"error": str(e)})


def main():
    """Main entry point for the MCP server."""
    parser = argparse.ArgumentParser(
        description="PDF Redaction MCP Server - Provides PDF redaction tools via Model Context Protocol",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Transport Modes:
  stdio       Standard I/O (default) - for Claude Desktop, Cursor, etc.
  http        HTTP transport - for web-based clients
  sse         Server-Sent Events - for mobile apps and remote clients

Examples:
  %(prog)s                                    # Run in STDIO mode (default)
  %(prog)s --transport sse --port 8000        # Run as SSE server on port 8000
  %(prog)s --transport http --host 0.0.0.0    # Run as HTTP server on all interfaces
  %(prog)s --pdf-dir /path/to/pdfs            # Set base directory for PDF files
        """
    )
    
    parser.add_argument(
        "--transport",
        type=str,
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="Transport mode for the MCP server (default: stdio)"
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to for HTTP/SSE mode (default: 127.0.0.1)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on for HTTP/SSE mode (default: 8000)"
    )
    
    parser.add_argument(
        "--pdf-dir",
        type=str,
        default=None,
        help="Base directory for PDF files. Relative paths in tools will be resolved against this directory."
    )
    
    args = parser.parse_args()
    
    # Set global PDF base directory if provided
    global PDF_BASE_DIR
    if args.pdf_dir:
        PDF_BASE_DIR = Path(args.pdf_dir).resolve()
        # stderr: in stdio mode stdout carries the JSON-RPC stream, so any
        # diagnostic printed there corrupts the protocol
        if not PDF_BASE_DIR.exists():
            print(f"Warning: PDF base directory does not exist: {PDF_BASE_DIR}", file=sys.stderr)
        else:
            print(f"PDF base directory: {PDF_BASE_DIR}", file=sys.stderr)

    # Run server with appropriate transport
    if args.transport == "stdio":
        print("Starting PDF Redaction MCP Server in STDIO mode...", file=sys.stderr)
        mcp.run()
    elif args.transport in ("http", "sse"):
        print(f"Starting PDF Redaction MCP Server in {args.transport.upper()} mode...")
        print(f"Listening on {args.host}:{args.port}")
        middleware = [
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],  # Allow all origins; use specific origins for security
                allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                allow_headers=[
                    "mcp-protocol-version",
                    "mcp-session-id",
                    "Authorization",
                    "Content-Type",
                ],
                expose_headers=["mcp-session-id"],            )
        ]
        app = mcp.http_app(middleware=middleware)
        
        uvicorn.run(app, host=args.host, port=args.port)
        #mcp.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
