from datetime import timedelta

from temporalio import workflow


@workflow.defn(name="RunMechModelWorkflow")
class RunMechModelWorkflow:
    @workflow.run
    async def run(self, simulation_run_id: str) -> None:
        await workflow.execute_activity(
            "run_mech_model_activity",
            simulation_run_id,
            start_to_close_timeout=timedelta(minutes=1),
        )
