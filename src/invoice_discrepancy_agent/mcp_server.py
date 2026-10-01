"""MCP server exposing this project's CrewAI tools (tools.py) plus the Week 4 MCP server's tools
(lookup_country, calculate, analyze_text), so the MCP Inspector shows them all in one session.

    npx @modelcontextprotocol/inspector .venv/bin/invoice-mcp-server

Relative PDF paths resolve against the project root, so `sample_invoice.pdf` works as-is.
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .crew import MCP_SERVER_DIR
from .tools import ContractTermsTool, DiscrepancyCalculatorTool, InvoiceParserTool, PdfTextTool

ROOT = Path(__file__).resolve().parents[2]

mcp = FastMCP("invoice-discrepancy-tools")

PdfPath = Annotated[str, Field(description="Path to the PDF file, absolute or relative to the project root.")]


def _resolve(path: str) -> str:
    p = Path(path).expanduser()
    return str(p if p.is_absolute() else ROOT / p)


@mcp.tool(name=PdfTextTool().name, description=PdfTextTool().description)
def pdf_text_reader(pdf_path: PdfPath = "sample_invoice.pdf") -> str:
    return PdfTextTool()._run(_resolve(pdf_path))


@mcp.tool(name=ContractTermsTool().name, description=ContractTermsTool().description)
def contract_terms_parser(pdf_path: PdfPath = "purchase_terms_conditions.pdf") -> str:
    return ContractTermsTool()._run(_resolve(pdf_path))


@mcp.tool(name=InvoiceParserTool().name, description=InvoiceParserTool().description)
def invoice_parser(pdf_path: PdfPath = "sample_invoice.pdf") -> str:
    return InvoiceParserTool()._run(_resolve(pdf_path))


@mcp.tool(name=DiscrepancyCalculatorTool().name, description=DiscrepancyCalculatorTool().description)
def discrepancy_calculator(
    contract_pdf_path: PdfPath = "purchase_terms_conditions.pdf",
    invoice_pdf_path: PdfPath = "sample_invoice.pdf",
) -> str:
    return DiscrepancyCalculatorTool()._run(_resolve(contract_pdf_path), _resolve(invoice_pdf_path))


def _add_week4_tools() -> None:
    """Register the Week 4 server's tool functions here; skipped if the server is not installed."""
    script = MCP_SERVER_DIR / "server.py"
    if not script.exists():
        logging.getLogger(__name__).warning("Week 4 MCP server not found at %s; serving tools.py only.", MCP_SERVER_DIR)
        return
    spec = importlib.util.spec_from_file_location("week4_mcp_server", script)
    week4 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(week4)
    for name in ("lookup_country", "calculate", "analyze_text"):
        mcp.add_tool(getattr(week4, name))


_add_week4_tools()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
