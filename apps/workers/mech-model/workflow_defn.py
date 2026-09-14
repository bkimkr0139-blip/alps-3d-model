from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn(name="RunMechModelWorkflow")
class RunMechModelWorkflow:
    @workflow.run
    async def run(self, simulation_run_id: str) -> None:
        # The field-twin model types are long-running (the surrogate DOE is
        # ~114 solver solves ≈ 6 min; a solver-engine replay several minutes
        # more) — the legacy 1-minute start_to_close timeout would kill them
        # mid-solve and Temporal would retry from scratch forever.
        # RetryPolicy: transient DB/MinIO blips retry twice with backoff;
        # deterministic ValueErrors (bad model_type/scenario) burn their
        # attempts fast and land in run.error_message — by design.
        await workflow.execute_activity(
            "run_mech_model_activity",
            simulation_run_id,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=2, initial_interval=timedelta(seconds=2), maximum_interval=timedelta(seconds=30)),
        )
