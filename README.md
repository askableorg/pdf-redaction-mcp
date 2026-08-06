# PDF Redaction MCP Server

A Model Context Protocol (MCP) server that provides comprehensive PDF redaction capabilities using [FastMCP](https://github.com/jlowin/fastmcp) and [pymupdf](https://pymupdf.readthedocs.io/).

## Features

This MCP server enables LLMs to:

- **Session-based in-memory operations** - load PDFs once and perform multiple operations without repeated file I/O
- **Load and save PDFs** - explicit control over when documents are read from and written to disk
- **Extract text from PDFs** in multiple formats (plain text, JSON, or structured blocks)
- **Search for text patterns** using exact match or regex with location information
- **Redact text by search** - automatically find and redact all occurrences of specified strings
- **Redact by coordinates** - precisely redact specific areas of a PDF
- **Redact images** - remove images from PDFs with customisable overlays
- **Verify redactions** - confirm that sensitive information has been properly removed
- **Get PDF information** - retrieve metadata and structure information

## Installation

### Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Using uv (Recommended)

```bash
# Clone or download the project
cd pdf-redaction-mcp

# Install dependencies
uv sync

# Run the server
uv run pdf-redaction-mcp
```

### Using pip

```bash
pip install -e .
pdf-redaction-mcp
```

## Usage

### Running the Server

The server supports multiple transport modes and configurations via command-line flags:

```bash
# Show all available options
uv run pdf-redaction-mcp --help

# STDIO mode (default) - for desktop clients
uv run pdf-redaction-mcp

# SSE mode - for mobile apps and remote clients
uv run pdf-redaction-mcp --transport sse --port 8000

# HTTP mode - for web-based clients  
uv run pdf-redaction-mcp --transport http --host 0.0.0.0 --port 8080

# With custom PDF directory (relative paths resolved against this)
uv run pdf-redaction-mcp --pdf-dir /path/to/pdfs

# Combined options
uv run pdf-redaction-mcp --transport sse --port 8000 --pdf-dir ~/Documents/pdfs
```

#### Command-Line Options

- `--transport {stdio,http,sse}`: Transport mode (default: stdio)
- `--host HOST`: Host to bind to for HTTP/SSE mode (default: 127.0.0.1)
- `--port PORT`: Port to listen on for HTTP/SSE mode (default: 8000)
- `--pdf-dir PDF_DIR`: Base directory for PDF files. Relative paths in tools will be resolved against this directory.

### Available Tools

All tools work with in-memory PDF documents using a session-based workflow:
1. **Load** a PDF into memory with `load_pdf`
2. **Operate** on it with any of the tools below
3. **Save** changes to disk with `save_pdf`

This approach avoids repeated file I/O and allows multiple operations on the same document efficiently.

---

#### 1. `load_pdf`

Load a PDF file into memory for session-based operations.

**Parameters:**
- `pdf_path` (str): Path to the PDF file to load
- `document_id` (str, optional): Identifier for this document (defaults to filename)

**Returns:** JSON with document_id and basic info

**Example:**
```python
load_pdf(
    pdf_path="/path/to/document.pdf",
    document_id="my_doc"
)
# Returns: {"document_id": "my_doc", "pages": 10, "status": "loaded"}
```

#### 2. `save_pdf`

Save an in-memory PDF document to disk.

**Parameters:**
- `document_id` (str): Identifier of the loaded document
- `output_path` (str): Path where the PDF will be saved

**Returns:** JSON with save confirmation

**Example:**
```python
save_pdf(
    document_id="my_doc",
    output_path="/path/to/output.pdf"
)
```

#### 3. `close_pdf`

Close and remove an in-memory PDF document to free memory.

**Parameters:**
- `document_id` (str): Identifier of the loaded document

**Returns:** JSON with close confirmation

**Example:**
```python
close_pdf(document_id="my_doc")
```

#### 4. `list_loaded_pdfs`

List all currently loaded PDF documents in memory.

**Returns:** JSON with information about all loaded documents

**Example:**
```python
list_loaded_pdfs()
# Returns: {"total_documents": 2, "documents": [{...}, {...}]}
```

#### 5. `extract_text_from_pdf`

Extract text from a loaded PDF document.

**Parameters:**
- `document_id` (str): Identifier of the loaded document
- `page_number` (int, optional): Specific page to extract (0-indexed)
- `format` (str): Output format - "text", "json", or "blocks"

**Example:**
```python
# Load document first
load_pdf(pdf_path="/path/to/document.pdf", document_id="doc1")

# Extract all text
extract_text_from_pdf(
    document_id="doc1",
    format="text"
)

# Extract specific page as JSON
extract_text_from_pdf(
    document_id="doc1",
    page_number=0,
    format="json"
)
```

#### 6. `search_text_in_pdf`

Search for text patterns and get their locations in a loaded PDF document.

**Parameters:**
- `document_id` (str): Identifier of the loaded document
- `search_string` (str): Text or regex pattern to search for
- `case_sensitive` (bool): Whether search should be case sensitive
- `use_regex` (bool): Whether to treat search_string as regex
- `page_number` (int, optional): Specific page to search

**Example:**
```python
# Load document first
load_pdf(pdf_path="/path/to/document.pdf", document_id="doc1")

# Search for email addresses using regex
search_text_in_pdf(
    document_id="doc1",
    search_string=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    use_regex=True
)
```

#### 7. `redact_text_by_search`

Automatically find and redact all occurrences of specified strings in a loaded PDF document.

**Parameters:**
- `document_id` (str): Identifier of the loaded document
- `search_strings` (List[str]): List of strings to redact
- `fill_color` (Tuple[float, float, float]): RGB colour (0-1 range)
- `overlay_text` (str): Optional text over redacted area
- `text_color` (Tuple[float, float, float]): RGB colour for overlay text

**Example:**
```python
# Load document
load_pdf(pdf_path="/path/to/input.pdf", document_id="doc1")

# Redact sensitive information (modifies in-memory document)
redact_text_by_search(
    document_id="doc1",
    search_strings=["CONFIDENTIAL", "john.doe@example.com", "123-45-6789"],
    fill_color=(0, 0, 0),  # Black
    overlay_text="[REDACTED]"
)

# Save the redacted document
save_pdf(document_id="doc1", output_path="/path/to/redacted.pdf")
```

#### 8. `redact_by_coordinates`

Redact specific areas by their exact coordinates in a loaded PDF document.

**Parameters:**
- `document_id` (str): Identifier of the loaded document
- `redactions` (List[Dict]): List of redaction areas with page, bbox, optional text, and optional `remove_text` (default `true`; `false` clears the covered pixels and vector art but leaves every glyph the rectangle overlaps standing)
- `fill_color` (Tuple[float, float, float]): RGB colour
- `overlay_text` (str): Default overlay text

**Example:**
```python
# Load document
load_pdf(pdf_path="/path/to/input.pdf", document_id="doc1")

# Redact specific areas (modifies in-memory document)
redact_by_coordinates(
    document_id="doc1",
    redactions=[
        {"page": 0, "bbox": [100, 100, 300, 150], "text": "REDACTED"},
        {"page": 1, "bbox": [50, 200, 250, 250]}
    ],
    fill_color=(0, 0, 0)
)

# Save the redacted document
save_pdf(document_id="doc1", output_path="/path/to/redacted.pdf")
```

#### 9. `redact_images_in_pdf`

Remove all images from specified pages of a loaded PDF document.

**Parameters:**
- `document_id` (str): Identifier of the loaded document
- `page_numbers` (List[int], optional): Pages to process (all if None)
- `fill_color` (Tuple[float, float, float]): RGB colour
- `overlay_text` (str): Text over redacted images

**Example:**
```python
# Load document
load_pdf(pdf_path="/path/to/input.pdf", document_id="doc1")

# Redact all images on first two pages (modifies in-memory document)
redact_images_in_pdf(
    document_id="doc1",
    page_numbers=[0, 1],
    overlay_text="[IMAGE REMOVED]"
)

# Save the redacted document
save_pdf(document_id="doc1", output_path="/path/to/no_images.pdf")
```

#### 10. `verify_redactions`

Verify that redactions were applied correctly by comparing two loaded PDF documents.

**Parameters:**
- `original_document_id` (str): Identifier of the original document
- `redacted_document_id` (str): Identifier of the redacted document
- `search_strings` (List[str], optional): Strings that should be gone

**Example:**
```python
# Load both documents
load_pdf(pdf_path="/path/to/original.pdf", document_id="original")
load_pdf(pdf_path="/path/to/redacted.pdf", document_id="redacted")

# Verify sensitive data was removed
verify_redactions(
    original_document_id="original",
    redacted_document_id="redacted",
    search_strings=["CONFIDENTIAL", "secret@example.com"]
)
```

#### 11. `get_pdf_info`

Get metadata and structure information about a loaded PDF document.

**Parameters:**
- `document_id` (str): Identifier of the loaded document

**Example:**
```python
# Load document first
load_pdf(pdf_path="/path/to/document.pdf", document_id="doc1")

# Get PDF information
get_pdf_info(document_id="doc1")
```

---

## Configuration

This section covers how to configure the PDF Redaction MCP Server with various MCP clients.

**Quick Links:**
- [Claude Desktop](#claude-desktop) - Most common desktop setup
- [Cursor IDE](#cursor-ide) - For developers using Cursor
- [Cline (VSCode)](#cline-vscode-extension) - VSCode MCP extension
- [Other MCP Clients](#other-mcp-clients) - Generic STDIO configuration

---

### Claude Desktop

Add to your `claude_desktop_config.json`:

**Basic Configuration (STDIO mode):**

```json
{
  "mcpServers": {
    "pdf-redaction": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/pdf-redaction-mcp",
        "run",
        "pdf-redaction-mcp"
      ]
    }
  }
}
```

**With Custom PDF Directory:**

```json
{
  "mcpServers": {
    "pdf-redaction": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/pdf-redaction-mcp",
        "run",
        "pdf-redaction-mcp",
        "--pdf-dir",
        "/Users/yourname/Documents/PDFs"
      ]
    }
  }
}
```

This allows you to use relative paths like `"document.pdf"` instead of full paths.

### Cursor IDE

Add to your `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "pdf-redaction": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/pdf-redaction-mcp",
        "run",
        "pdf-redaction-mcp"
      ]
    }
  }
}
```

### Cline (VSCode Extension)

Add to your Cline MCP settings:

```json
{
  "mcpServers": {
    "pdf-redaction": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/pdf-redaction-mcp",
        "run",
        "pdf-redaction-mcp",
        "--pdf-dir",
        "${workspaceFolder}/pdfs"
      ]
    }
  }
}
```

### Other MCP Clients

For any MCP client supporting STDIO transport, use:

**Command:** `uv`

**Args:**
```
--directory /path/to/pdf-redaction-mcp
run
pdf-redaction-mcp
[optional flags like --pdf-dir]
```

### Environment Variables (Optional)

For production deployments, you can use environment variables:

```bash
# Set PDF directory via environment
export PDF_DIR=/var/pdfs

# Then reference in your startup script
uv run pdf-redaction-mcp --pdf-dir "$PDF_DIR"
```

### Real-World Configuration Examples

**Example 1: Personal Use with Claude Desktop**

Store all PDFs in your Documents folder:

```json
{
  "mcpServers": {
    "pdf-redaction": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/yourname/workspace/pdf-redaction-mcp",
        "run",
        "pdf-redaction-mcp",
        "--pdf-dir",
        "/Users/yourname/Documents"
      ]
    }
  }
}
```

Now you can say: *"Redact emails from report.pdf"* instead of using full paths.

**Example 2: Team Deployment with Shared PDFs**

Deploy remotely with network-mounted PDF storage:

```bash
# On your server
uv run pdf-redaction-mcp \
  --transport sse \
  --host 0.0.0.0 \
  --port 8000 \
  --pdf-dir /mnt/shared-pdfs
```

Team members configure their clients to use the remote server.

**Example 3: Development Setup**

Use project-relative paths during development:

```json
{
  "mcpServers": {
    "pdf-redaction": {
      "command": "uv",
      "args": [
        "--directory",
        "${workspaceFolder}/pdf-redaction-mcp",
        "run",
        "pdf-redaction-mcp",
        "--pdf-dir",
        "${workspaceFolder}/test-pdfs"
      ]
    }
  }
}
```

---

## Workflow Examples

### Example 1: Redact Personal Information

**Session-based workflow (new approach):**
```
User: "Please redact all email addresses and phone numbers from report.pdf"

1. LLM loads the document:
   load_pdf(pdf_path="report.pdf", document_id="report")

2. LLM searches for patterns:
   search_text_in_pdf(
     document_id="report",
     search_string=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
     use_regex=True
   )

3. LLM redacts in-memory:
   redact_text_by_search(
     document_id="report",
     search_strings=["john@example.com", "555-123-4567", ...]
   )

4. LLM saves the result:
   save_pdf(document_id="report", output_path="report_redacted.pdf")

5. LLM reports: "Successfully redacted 5 email addresses and 3 phone numbers"
```

**Benefits of session-based approach:**
- PDF loaded once, multiple operations performed
- No repeated file I/O
- Can verify, modify, and re-verify without reloading

### Example 2: Redact Specific Section

```
1. User: "Redact the financial table on page 3 of the report"

2. LLM loads document:
   load_pdf(pdf_path="report.pdf", document_id="report")

3. LLM extracts page structure:
   extract_text_from_pdf(document_id="report", page_number=2, format="blocks")

4. LLM identifies table coordinates from block structure

5. LLM redacts in-memory:
   redact_by_coordinates(
     document_id="report",
     redactions=[{"page": 2, "bbox": [100, 200, 500, 400]}]
   )

6. LLM verifies by extracting text again:
   extract_text_from_pdf(document_id="report", page_number=2)

7. LLM saves:
   save_pdf(document_id="report", output_path="report_redacted.pdf")
```

### Example 3: Remove All Images

```
1. User: "Remove all images from the document but keep the text"

2. LLM loads document:
   load_pdf(pdf_path="document.pdf", document_id="doc")

3. LLM checks for images:
   get_pdf_info(document_id="doc")

4. LLM redacts images:
   redact_images_in_pdf(document_id="doc")

5. LLM verifies and saves:
   get_pdf_info(document_id="doc")  # Verify images are gone
   save_pdf(document_id="doc", output_path="document_no_images.pdf")
   
6. LLM cleans up:
   close_pdf(document_id="doc")  # Free memory
```

### Example 4: Multi-Step Verification Workflow

```
1. User: "Redact all SSNs, then verify they're gone, then redact names too"

2. LLM loads document:
   load_pdf(pdf_path="sensitive.pdf", document_id="sensitive")

3. LLM redacts SSNs:
   redact_text_by_search(
     document_id="sensitive",
     search_strings=[r"\d{3}-\d{2}-\d{4}"],
     use_regex=True
   )

4. LLM creates checkpoint by saving:
   save_pdf(document_id="sensitive", output_path="sensitive_step1.pdf")

5. LLM loads original for comparison:
   load_pdf(pdf_path="sensitive.pdf", document_id="original")

6. LLM verifies:
   verify_redactions(
     original_document_id="original",
     redacted_document_id="sensitive",
     search_strings=["123-45-6789", "987-65-4321"]
   )

7. LLM continues with name redaction:
   redact_text_by_search(
     document_id="sensitive",
     search_strings=["John Doe", "Jane Smith"]
   )

8. LLM saves final version:
   save_pdf(document_id="sensitive", output_path="sensitive_final.pdf")

9. LLM cleans up:
   close_pdf(document_id="original")
   close_pdf(document_id="sensitive")
```

4. LLM verifies using get_pdf_info that images are gone
```



---

## Troubleshooting

### Claude Desktop Connection Issues

**Problem:** MCP server not connecting in Claude Desktop

**Solutions:**
1. Verify the path in `claude_desktop_config.json` is correct:
   ```bash
   # Check if the directory exists
   ls -la /path/to/pdf-redaction-mcp
   ```

2. Test the server manually:
   ```bash
   cd /path/to/pdf-redaction-mcp
   uv run pdf-redaction-mcp --help
   ```

3. Check Claude Desktop logs:
   - macOS: `~/Library/Logs/Claude/`
   - Windows: `%APPDATA%\Claude\logs\`
   - Linux: `~/.config/Claude/logs/`

### PDF Path Issues

**Problem:** "File not found" errors when using relative paths

**Solution:** Configure `--pdf-dir` flag in your MCP client config:
```json
{
  "mcpServers": {
    "pdf-redaction": {
      "command": "uv",
      "args": [
        "--directory", "/path/to/pdf-redaction-mcp",
        "run", "pdf-redaction-mcp",
        "--pdf-dir", "/your/pdf/directory"
      ]
    }
  }
}
```

### Port Already in Use (HTTP/SSE mode)

**Problem:** `Address already in use` error when starting server

**Solution:** 
1. Use a different port:
   ```bash
   uv run pdf-redaction-mcp --transport sse --port 8001
   ```

2. Or find and kill the process using the port:
   ```bash
   # macOS/Linux
   lsof -ti:8000 | xargs kill -9
   
   # Windows
   netstat -ano | findstr :8000
   taskkill /PID <PID> /F
   ```

### UV Not Found

**Problem:** `uv: command not found`

**Solution:** Install UV package manager:
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or use pip
pip install uv
```

---

## Development

### Running Tests

```bash
uv run pytest
```

### Project Structure

```
pdf-redaction-mcp/
├── src/
│   └── pdf_redaction_mcp/
│       ├── __init__.py
│       └── server.py          # Main MCP server implementation
├── tests/
│   └── test_server.py         # Unit tests
├── pyproject.toml             # Project dependencies
└── README.md                  # This file
```

## Technical Details

### Redaction Implementation

The server uses pymupdf's redaction annotations, which:

1. **Add redaction annotations** to mark areas for removal
2. **Apply redactions** to permanently remove content
3. **Cannot be undone** once saved - content is truly deleted from PDF structure

### Colour Format

Colours are specified as RGB tuples with values from 0 to 1:
- Black: `(0, 0, 0)`
- White: `(1, 1, 1)`
- Red: `(1, 0, 0)`
- Green: `(0, 1, 0)`
- Blue: `(0, 0, 1)`

### Coordinate System

PDF coordinates use bottom-left origin:
- `x0, y0`: Bottom-left corner of rectangle
- `x1, y1`: Top-right corner of rectangle

Bounding boxes: `[x0, y0, x1, y1]`

## Security Considerations

1. **Permanent Removal**: Redactions permanently remove content from PDF structure
2. **Verify Redactions**: Always use `verify_redactions` to confirm sensitive data is gone
3. **Backup Original**: Keep original files backed up before redacting
4. **File Paths**: Ensure proper file path validation in production
5. **Access Control**: Implement appropriate access controls for sensitive documents

## Limitations

- Only works with PDF files (use pymupdf's supported formats)
- Encrypted PDFs may require password authentication
- Very large PDFs may require significant memory
- Redactions are permanent once saved

## Contributing

Contributions are welcome! Please ensure:

1. Code follows existing style
2. Tests pass (`uv run pytest`)
3. Documentation is updated
4. Commit messages are clear

## Licence

MIT Licence - see LICENCE file for details

## Acknowledgements

- [FastMCP](https://github.com/jlowin/fastmcp) - MCP framework
- [pymupdf](https://pymupdf.readthedocs.io/) - PDF manipulation library
- [Model Context Protocol](https://modelcontextprotocol.io/) - MCP specification

## Support

For issues, questions, or contributions:
- Open an issue on GitHub
- Check the [FastMCP documentation](https://github.com/jlowin/fastmcp)
- Check the [pymupdf documentation](https://pymupdf.readthedocs.io/)
