"""Temporal worker for the spice-worker task queue (FR-04). Run with:

    apps/workers/spice-worker/.venv/bin/python worker.py
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from activities import run_spice_analysis_activity
from workflow_defn import RunSpiceAnalysisWorkflow

TASK_QUEUE = "spice-worker"


async def main() -> None:
    client = await Client.connect("localhost:7233")
    with ThreadPoolExecutor(max_workers=8) as executor:
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[RunSpiceAnalysisWorkflow],
            activities=[run_spice_analysis_activity],
            activity_executor=executor,
        )
        print(f"spice-worker listening on task queue '{TASK_QUEUE}'")
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
