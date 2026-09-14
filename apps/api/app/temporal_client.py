from temporalio.client import Client

TEMPORAL_TARGET = "localhost:7233"

_client: Client | None = None


async def get_temporal_client() -> Client:
    global _client
    if _client is None:
        _client = await Client.connect(TEMPORAL_TARGET)
    return _client
