"""Temporal worker for the CAD-conversion task queue (§8.1 Simulation
Orchestrator). Run with:

    apps/workers/cad-converter/.venv/bin/python worker.py
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from activities import convert_step_to_gltf_activity
from workflow_defn import ConvertStepToGltfWorkflow

TASK_QUEUE = "cad-converter"


async def main() -> None:
    client = await Client.connect("localhost:7233")
    with ThreadPoolExecutor(max_workers=8) as executor:
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[ConvertStepToGltfWorkflow],
            activities=[convert_step_to_gltf_activity],
            activity_executor=executor,
        )
        print(f"cad-converter worker listening on task queue '{TASK_QUEUE}'")
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
