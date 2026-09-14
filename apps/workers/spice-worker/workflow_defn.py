"""Kept import-light for the same reason as cad-converter's workflow_defn.py:
Temporal's sandbox re-imports whatever module defines the workflow class."""

from datetime import timedelta

from temporalio import workflow


@workflow.defn(name="RunSpiceAnalysisWorkflow")
class RunSpiceAnalysisWorkflow:
    @workflow.run
    async def run(self, simulation_run_id: str) -> None:
        await workflow.execute_activity(
            "run_spice_analysis_activity",
            simulation_run_id,
            start_to_close_timeout=timedelta(minutes=2),
        )
