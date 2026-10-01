# Contract vs. Invoice Discrepancy Agent (CrewAI)

A CrewAI crew that reads `purchase_terms_conditions.pdf` and `sample_invoice.pdf`,
extracts the contract terms and invoice data, compares every invoice line item against
the contracted price, and writes a Markdown discrepancy report.

## How it works

Four agents run sequentially:

| Agent | Tools | Output |
|---|---|---|
| Procurement Contract Analyst | `contract_terms_parser`, `pdf_text_reader` | `ContractTerms` (items, unit prices, Net days, tax clause) |
| Accounts Payable Invoice Analyst | `invoice_parser`, `pdf_text_reader` | `InvoiceData` (lines, qty, prices, tax, totals, dates) |
| Invoice Compliance Auditor | `discrepancy_calculator`, `pdf_text_reader`, `calculate` (MCP) | `DiscrepancyReport` (per-item variance, severity, checks) |
| Audit Report Writer | `analyze_text` (MCP) | `output/discrepancy_report.md` |

Tools marked (MCP) come from the [Week 4 MCP server](https://github.com/Qiqi077-Tech/Week4-MCP_Server),
which the crew launches over stdio: the auditor uses `calculate` once for the net financial impact, and
the writer uses `analyze_text` to keep the executive summary under 120 words. The crew still runs without
it, minus those two tools (see [Week 4 MCP server](#week-4-mcp-server-optional) below).

PDFs are read with LlamaIndex's `PDFReader` (local, no extra API key). All arithmetic runs in
deterministic Python (`parsing.py`), exposed to agents as tools, so the LLM never invents numbers. The agents verify the parsed data against the raw PDF text and write the narrative.

Checks performed:

- Unit price per item vs. contract (over/undercharge, % and line impact)
- Items billed that are not in the contract, and contracted items not billed
- Line math (qty x price), subtotal, tax rate x subtotal, total
- Payment terms (Net days), due date = invoice date + Net days, payment method
- Invoice number and vendor vs. the contract reference
- Offsetting errors: flags when a correct-looking total hides line-level errors

## Setup

```bash
uv venv -p 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
cp .env.example .env   # add your GOOGLE_API_KEY; MODEL defaults to gemini/gemini-3.5-flash-lite
```

### Week 4 MCP server (optional)

Clone it into the same parent folder as this project, keeping the folder name, and give it its own venv:

```bash
cd ..   # the folder that contains this project
git clone https://github.com/Qiqi077-Tech/Week4-MCP_Server.git
cd Week4-MCP_Server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # Windows: .venv\Scripts\pip install -r requirements.txt
```

The crew finds it at `../Week4-MCP_Server` automatically. If you cloned it elsewhere, set
`MCP_SERVER_DIR` in `.env` to its absolute path. If it is missing, the crew logs
`MCP server not found at ...` and runs without `calculate` and `analyze_text`.

## Run

```bash
# Full multi-agent CrewAI run (needs GOOGLE_API_KEY in .env)
.venv/bin/python -m invoice_discrepancy_agent.main

# Deterministic report without an LLM
.venv/bin/python -m invoice_discrepancy_agent.main --offline

# Other documents
.venv/bin/python -m invoice_discrepancy_agent.main --contract path/terms.pdf --invoice path/invoice.pdf
```

Outputs go to `output/`: `discrepancy_report.md` and `discrepancy_findings.json`.

## Inspect the tools over MCP

`mcp_server.py` exposes the four tools above as a stdio MCP server (relative PDF paths resolve
against the project root):

```bash
npx @modelcontextprotocol/inspector .venv/bin/invoice-mcp-server
```

## Tests

```bash
.venv/bin/python -m pytest -q
```
