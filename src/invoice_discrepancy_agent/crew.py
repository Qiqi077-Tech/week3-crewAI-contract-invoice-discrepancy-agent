"""The CrewAI crew: four agents run sequentially from extraction to report."""
from __future__ import annotations

import os

from crewai import LLM, Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from .models import ContractTerms, DiscrepancyReport, InvoiceData
from .tools import ContractTermsTool, DiscrepancyCalculatorTool, InvoiceParserTool, PdfTextTool

DEFAULT_MODEL = "gemini/gemini-2.5-flash"


def build_llm() -> LLM:
    return LLM(model=os.getenv("MODEL", DEFAULT_MODEL), temperature=0)


@CrewBase
class InvoiceDiscrepancyCrew:
    """Contract vs. invoice discrepancy crew."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self) -> None:
        self.llm = build_llm()

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
                     tools=[DiscrepancyCalculatorTool(), PdfTextTool()], verbose=True)

    @agent
    def report_writer(self) -> Agent:
        return Agent(config=self.agents_config["report_writer"], llm=self.llm, verbose=True)

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
