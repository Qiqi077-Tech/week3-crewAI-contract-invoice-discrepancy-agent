"""The CrewAI crew: four agents run sequentially from extraction to report."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from crewai import LLM, Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from mcp import StdioServerParameters

from .models import ContractTerms, DiscrepancyReport, InvoiceData
from .tools import ContractTermsTool, DiscrepancyCalculatorTool, InvoiceParserTool, PdfTextTool

DEFAULT_MODEL = "gemini/gemini-2.5-flash"

# Week 4 MCP server (https://github.com/Qiqi077-Tech/Week4-MCP_Server), cloned next to this repo
# by default. Override with MCP_SERVER_DIR. It provides the `calculate` and `analyze_text` tools.
MCP_SERVER_DIR = Path(os.getenv("MCP_SERVER_DIR", Path(__file__).resolve().parents[3] / "Week4-MCP_Server"))

log = logging.getLogger(__name__)


def build_llm() -> LLM:
    return LLM(model=os.getenv("MODEL", DEFAULT_MODEL), temperature=0)


def build_mcp_server_params() -> StdioServerParameters | None:
    """Launch the MCP server over stdio with its own venv; None if it is not installed."""
    python, script = MCP_SERVER_DIR / ".venv" / "bin" / "python", MCP_SERVER_DIR / "server.py"
    if not (python.exists() and script.exists()):
        log.warning("MCP server not found at %s; running without MCP tools.", MCP_SERVER_DIR)
        return None
    return StdioServerParameters(command=str(python), args=[str(script)])


@CrewBase
class InvoiceDiscrepancyCrew:
    """Contract vs. invoice discrepancy crew."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self) -> None:
        self.llm = build_llm()
        # CrewBase starts the server on the first get_mcp_tools() call and stops it after kickoff.
        self.mcp_server_params = build_mcp_server_params()

    @agent
    def contract_analyst(self) -> Agent:
        return Agent(config=self.agents_config["contract_analyst"], llm=self.llm,
                     tools=[ContractTermsTool(), PdfTextTool()], verbose=True)

    @agent
    def invoice_analyst(self) -> Agent:
        return Agent(config=self.agents_config["invoice_analyst"], llm=self.llm,
                     tools=[InvoiceParserTool(), PdfTextTool()], verbose=True)

    @agent
    def discrepancy_auditor(self) -> Agent:
        return Agent(config=self.agents_config["discrepancy_auditor"], llm=self.llm,
                     tools=[DiscrepancyCalculatorTool(), PdfTextTool(), *self.get_mcp_tools("calculate")],
                     verbose=True)

    @agent
    def report_writer(self) -> Agent:
        return Agent(config=self.agents_config["report_writer"], llm=self.llm,
                     tools=self.get_mcp_tools("analyze_text"), verbose=True)

    @task
    def extract_contract_terms(self) -> Task:
        return Task(config=self.tasks_config["extract_contract_terms"], output_pydantic=ContractTerms)

    @task
    def extract_invoice_data(self) -> Task:
        return Task(config=self.tasks_config["extract_invoice_data"], output_pydantic=InvoiceData)

    @task
    def audit_discrepancies(self) -> Task:
        return Task(
            config=self.tasks_config["audit_discrepancies"],
            context=[self.extract_contract_terms(), self.extract_invoice_data()],
            output_pydantic=DiscrepancyReport,
        )

    @task
    def write_report(self) -> Task:
        return Task(config=self.tasks_config["write_report"], context=[self.audit_discrepancies()])

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=True)
