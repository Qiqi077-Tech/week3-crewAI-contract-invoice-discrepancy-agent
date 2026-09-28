"""Command-line entry point.

    python -m invoice_discrepancy_agent.main                 # full CrewAI run (needs an LLM API key)
    python -m invoice_discrepancy_agent.main --offline       # deterministic report, no LLM
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .parsing import compare, extract_pdf_text, parse_contract, parse_invoice
from .report import render_markdown

ROOT = Path(__file__).resolve().parents[2]


def run(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    p = argparse.ArgumentParser(description="Compare an invoice against purchase terms and report discrepancies.")
    p.add_argument("--contract", default=str(ROOT / "purchase_terms_conditions.pdf"))
    p.add_argument("--invoice", default=str(ROOT / "sample_invoice.pdf"))
    p.add_argument("--output-dir", default=str(ROOT / "output"))
    p.add_argument("--offline", action="store_true", help="Skip the LLM crew; render the report deterministically.")
    args = p.parse_args(argv)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in (args.contract, args.invoice):
        if not Path(f).exists():
            print(f"File not found: {f}", file=sys.stderr)
            return 1

    invoice = parse_invoice(extract_pdf_text(args.invoice))
    findings = compare(parse_contract(extract_pdf_text(args.contract)), invoice)
    (out_dir / "discrepancy_findings.json").write_text(findings.model_dump_json(indent=2))

    report_path = out_dir / "discrepancy_report.md"
    if args.offline:
        report_path.write_text(render_markdown(findings, invoice))
    else:
        from .crew import DEFAULT_MODEL, InvoiceDiscrepancyCrew

        model = os.getenv("MODEL", DEFAULT_MODEL)
        key_vars = {"gemini": ("GOOGLE_API_KEY", "GEMINI_API_KEY"), "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
                    "anthropic": ("ANTHROPIC_API_KEY",), "openai": ("OPENAI_API_KEY",)}.get(model.split("/")[0], ())
        if key_vars and not any(os.getenv(k) for k in key_vars):
            print(f"{' or '.join(key_vars)} is not set for MODEL={model}. Add it to .env, or use --offline.",
                  file=sys.stderr)
            return 2

        crew = InvoiceDiscrepancyCrew()
        crew.tasks_config["write_report"]["output_file"] = str(report_path)
        result = crew.crew().kickoff(inputs={"contract_pdf": args.contract, "invoice_pdf": args.invoice})
        report_path.write_text(str(result.raw).strip() + "\n")
        print(f"\nModel: {model}")

    print(f"Report:   {report_path}")
    print(f"Findings: {out_dir / 'discrepancy_findings.json'}")
    print(json.dumps({"discrepancies": len(findings.discrepancies),
                      "overcharge": findings.total_overcharge,
                      "undercharge": findings.total_undercharge}))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
