from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    artifacts,
    asic,
    assistant,
    audit,
    baselines,
    components,
    correlations,
    doe,
    fa_capa,
    feedback,
    gates,
    model_canvas,
    products,
    process_monitoring,
    process_twin,
    requirements,
    simulation_runs,
    test_plans,
    test_runs,
    twins,
)
from app.telemetry import setup_telemetry

app = FastAPI(title="ALPS ALPINE Engineering Twin Workbench API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8090", "http://localhost:5173", "https://alps-twin.wizbase.ai.kr"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

setup_telemetry(app)

app.include_router(products.router)
app.include_router(components.router)
app.include_router(requirements.router)
app.include_router(baselines.router)
app.include_router(twins.router)
app.include_router(audit.router)
app.include_router(artifacts.router)
app.include_router(simulation_runs.router)
app.include_router(test_plans.router)
app.include_router(test_runs.router)
app.include_router(correlations.router)
app.include_router(gates.router)
app.include_router(model_canvas.router)
app.include_router(process_twin.router)
app.include_router(process_monitoring.router)
app.include_router(fa_capa.router)
app.include_router(asic.router)
app.include_router(doe.router)
app.include_router(feedback.router)
app.include_router(assistant.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
