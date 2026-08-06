# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Region redactions no longer paint over standing text** — `redact_by_coordinates`
  with `remove_text: false` used to create its annotations with `fill=fill_color`,
  so applying the redaction painted the rectangle even though `PDF_REDACT_TEXT_NONE`
  had deliberately left the overlapping text in place: the text stayed extractable
  but was invisible under the fill. Region-pass annotations are now created with
  `fill=False` (pymupdf treats `None` as default white; only `False` suppresses the
  fill). `fill_color` now applies to text redactions (`remove_text: true`) only.

### Removed
- **Base64 tools** - Removed all base64-encoded PDF tools as this MCP now only works with local files
  - Removed `extract_text_from_pdf_base64`
  - Removed `search_text_in_pdf_base64`
  - Removed `redact_text_by_search_base64`
  - Removed `redact_by_coordinates_base64`
  - Removed `redact_images_in_pdf_base64`
  - Removed `verify_redactions_base64`
  - Removed `get_pdf_info_base64`
- Removed `base64` and `io` module imports (no longer needed)
- Removed mobile app deployment documentation and examples
- Removed `examples/example_base64_usage.py`

### Changed
- Server now provides 7 tools (file-based only for local PDFs)
- Updated all documentation to reflect local-file-only usage
- Simplified architecture - single tool implementation pattern

## [0.2.0] - 2025-01-13

### Added
- **Base64 tools** for working with uploaded PDFs (mobile/web apps)
  - `extract_text_from_pdf_base64`
  - `search_text_in_pdf_base64`
  - `redact_text_by_search_base64`
  - `redact_by_coordinates_base64`
  - `redact_images_in_pdf_base64`
  - `verify_redactions_base64`
  - `get_pdf_info_base64`
- Support for in-memory PDF processing via base64 encoding
- Remote server deployment guide for HTTP/SSE transport
- Mobile app (Android/iOS) integration examples
- Documentation for when to use file-based vs base64 tools

### Changed
- Server now provides 14 tools total (7 file-based + 7 base64)
- Updated README with comprehensive base64 tool documentation
- Enhanced deployment section with cloud deployment examples

### Technical
- Added base64 and io module imports
- All base64 tools process PDFs entirely in memory
- Output PDFs returned as base64-encoded strings in JSON
- No filesystem access required for base64 tools

## [0.1.0] - 2025-01-13

### Added
- Initial release of PDF Redaction MCP Server
- FastMCP2-based server implementation
- Seven core tools for PDF manipulation:
  - `extract_text_from_pdf` - Extract text in multiple formats
  - `search_text_in_pdf` - Search with regex support
  - `redact_text_by_search` - Automatic text redaction
  - `redact_by_coordinates` - Precise area redaction
  - `redact_images_in_pdf` - Image removal
  - `verify_redactions` - Redaction verification
  - `get_pdf_info` - PDF metadata extraction
- Comprehensive error handling for all operations
- Support for STDIO and HTTP/SSE transports
- UV project structure with dependency management
- Complete test suite with pytest
- Documentation:
  - Comprehensive README with examples
  - Quick Start guide
  - Example usage scripts
- British English throughout codebase and documentation

### Features
- Search and redact using regular expressions
- Customisable redaction colours and overlay text
- Batch redaction across multiple pages
- Verification tools to confirm redactions
- Support for encrypted PDFs
- Multiple text extraction formats (text, JSON, blocks)

### Technical
- Built with FastMCP 2.x
- Uses pymupdf 1.24+ for PDF operations
- Python 3.10+ compatibility
- UV package manager integration
- Comprehensive type hints
- JSON-based error reporting
