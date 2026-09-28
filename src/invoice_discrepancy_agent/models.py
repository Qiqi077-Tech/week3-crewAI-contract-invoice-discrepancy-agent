"""Pydantic models shared by the tools, the crew tasks and the report renderer."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Severity = Literal["high", "medium", "low", "info"]


class ContractItem(BaseModel):
    description: str
    unit_price: float


class ContractTerms(BaseModel):
    vendor: Optional[str] = None
    invoice_reference: Optional[str] = None
    items: list[ContractItem] = Field(default_factory=list)
    payment_net_days: Optional[int] = None
    payment_methods: list[str] = Field(default_factory=list)
    tax_clause: Optional[str] = None
    other_terms: list[str] = Field(default_factory=list)


class InvoiceLine(BaseModel):
    description: str
    quantity: float
    unit_price: float
    amount: float


class InvoiceData(BaseModel):
    vendor: Optional[str] = None
    bill_to: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None  # ISO yyyy-mm-dd
    due_date: Optional[str] = None  # ISO yyyy-mm-dd
    payment_terms: Optional[str] = None
    payment_method: Optional[str] = None
    lines: list[InvoiceLine] = Field(default_factory=list)
    subtotal: Optional[float] = None
    tax_rate_percent: Optional[float] = None
    tax_amount: Optional[float] = None
    total_due: Optional[float] = None


class ItemComparison(BaseModel):
    invoice_description: str
    contract_description: Optional[str] = None
    quantity: float
    invoiced_unit_price: float
    contract_unit_price: Optional[float] = None
    unit_price_variance: Optional[float] = None
    invoiced_amount: float
    expected_amount: Optional[float] = None
    amount_variance: Optional[float] = None
    status: Literal["match", "overcharged", "undercharged", "not_in_contract", "math_error"]
    note: str = ""


class Discrepancy(BaseModel):
    category: str
    item: str
    expected: str
    actual: str
    variance: Optional[float] = None
    severity: Severity
    explanation: str


class DiscrepancyReport(BaseModel):
    invoice_number: Optional[str] = None
    vendor: Optional[str] = None
    buyer: Optional[str] = None
    item_comparisons: list[ItemComparison] = Field(default_factory=list)
    discrepancies: list[Discrepancy] = Field(default_factory=list)
    checks_passed: list[str] = Field(default_factory=list)
    invoiced_subtotal: Optional[float] = None
    expected_subtotal: Optional[float] = None
    invoiced_total: Optional[float] = None
    expected_total: Optional[float] = None
    total_overcharge: float = 0.0
    total_undercharge: float = 0.0
    recommendation: str = ""
