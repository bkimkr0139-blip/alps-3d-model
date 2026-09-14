"""Kept deliberately import-light: Temporal's sandbox re-imports whichever
module defines a @workflow.defn class to run it deterministically, and flags
any restricted call (e.g. pathlib.Path.resolve) made at module import time.
The activity is referenced by name so this file never imports app.* / OCP.
"""

from datetime import timedelta

from temporalio import workflow


@workflow.defn(name="ConvertStepToGltfWorkflow")
class ConvertStepToGltfWorkflow:
    @workflow.run
    async def run(self, simulation_run_id: str) -> None:
        await workflow.execute_activity(
            "convert_step_to_gltf_activity",
            simulation_run_id,
            start_to_close_timeout=timedelta(minutes=5),
        )
