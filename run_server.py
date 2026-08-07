#!/usr/bin/env python3
"""Run the PDF Redaction MCP Server in streamable HTTP mode for remote deployment.

This script starts the server in streamable HTTP mode, suitable for:
- Remote MCP connections
- Web-based clients

Usage:
    python run_server.py [--port PORT] [--host HOST]

Example:
    python run_server.py --port 8000 --host 0.0.0.0
"""

import argparse
from pdf_redaction_mcp.server import mcp


def main():
    parser = argparse.ArgumentParser(
        description="Run PDF Redaction MCP Server in streamable HTTP mode"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    
    args = parser.parse_args()
    
    print(f"Starting PDF Redaction MCP Server")
    print(f"Mode: Streamable HTTP")
    print(f"Host: {args.host}")
    print(f"Port: {args.port}")
    print(f"URL: http://{args.host}:{args.port}/mcp")
    print()
    print("Server features:")
    print("  • 7 tools for working with local PDF files")
    print()
    print("Compatible with:")
    print("  • Claude Desktop")
    print("  • Cursor IDE")
    print("  • Any MCP client with STDIO/HTTP transport")
    print()
    print("Press Ctrl+C to stop the server")
    print("-" * 60)
    
    # Run the server
    mcp.run(transport="http", port=args.port, host=args.host)


if __name__ == "__main__":
    main()
