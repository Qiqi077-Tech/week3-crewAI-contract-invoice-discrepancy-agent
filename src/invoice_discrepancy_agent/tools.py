"""CrewAI tools exposed to the agents."""
from __future__ import annotations

from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from .parsing import extract_pdf_text, parse_contract, parse_invoice, analyze_files


class PdfPathInput(BaseModel):
    pdf_path: str = Field(..., description="Path to the PDF file to read.")


class PdfTextTool(BaseTool):
    name: str = "pdf_text_reader"
    description: str = "Extract the full raw text of a PDF file. Input: pdf_path."
    args_schema: Type[BaseModel] = PdfPathInput

    def _run(self, pdf_path: str) -> str:
        if not Path(pdf_path).exists():
            return f"ERROR: file not found: {pdf_path}"
        return extract_pdf_text(pdf_path)


class ContractTermsTool(BaseTool):
    name: str = "contract_terms_parser"
    description: str = (
        "Parse a purchase terms & conditions PDF into structured JSON: contracted items and unit "
        "prices, payment net days, payment methods, tax clause, vendor and invoice reference."
    )
    args_schema: Type[BaseModel] = PdfPathInput

    def _run(self, pdf_path: str) -> str:
        return parse_contract(extract_pdf_text(pdf_path)).model_dump_json(indent=2)


class InvoiceParserTool(BaseTool):
    name: str = "invoice_parser"
    description: str = (
        "Parse an invoice PDF into structured JSON: header fields, line items (qty, unit price, "
        "amount), subtotal, tax rate, tax amount and total due."
    )
    args_schema: Type[BaseModel] = PdfPathInput

    def _run(self, pdf_path: str) -> str:
        return parse_invoice(extract_pdf_text(pdf_path)).model_dump_json(indent=2)


class CompareInput(BaseModel):
    contract_pdf_path: str = Field(..., description="Path to the purchase terms PDF.")
    invoice_pdf_path: str = Field(..., description="Path to the invoice PDF.")


class DiscrepancyCalculatorTool(BaseTool):
    name: str = "discrepancy_calculator"
    description: str = (
        "Deterministically compare an invoice against the purchase terms. Returns per-item price "
        "comparisons, every discrepancy with variance and severity, checks that passed, expected vs "
        "invoiced totals and a recommendation. Use this for all arithmetic."
    )
    args_schema: Type[BaseModel] = CompareInput

    def _run(self, contract_pdf_path: str, invoice_pdf_path: str) -> str:
        return analyze_files(contract_pdf_path, invoice_pdf_path).model_dump_json(indent=2)
