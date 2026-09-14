"""Temporal worker for the mech-model task queue (FR-05). Run with:

    apps/workers/mech-model/.venv/bin/python worker.py
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from activities import run_mech_model_activity
from workflow_defn import RunMechModelWorkflow

TASK_QUEUE = "mech-model"


async def main() -> None:
    client = await Client.connect("localhost:7233")
    with ThreadPoolExecutor(max_workers=8) as executor:
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[RunMechModelWorkflow],
            activities=[run_mech_model_activity],
            activity_executor=executor,
        )
        print(f"mech-model worker listening on task queue '{TASK_QUEUE}'")
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
