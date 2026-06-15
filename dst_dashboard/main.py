from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dst_dashboard.api import experiments, datasets, panels

app = FastAPI(
    title="DST Dashboard API",
    description="REST API for DST Dashboard",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(experiments.router)
app.include_router(datasets.router)
app.include_router(panels.router)


@app.get("/")
async def root():
    return {
        "service": "DST Dashboard API",
        "version": "0.1.0",
        "swagger": "/api/docs",
        "redoc": "/api/redoc",
        "openapi": "/api/openapi.json",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
