import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dst_dashboard.api import admin, datasets, datasources, experiments, panels
from dst_dashboard.config.constants import Constants
from dst_dashboard.config.utils import LoadConfig
from dst_dashboard.storage.db import DSTDatabase

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="DST Dashboard API",
    description="REST API for DST Dashboard",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)


@app.on_event("startup")
def on_startup():
    """
    Initialize application on startup.

    Experiments are managed exclusively through the API and live only in the
    database - config.yaml only defines datasources, so startup just loads
    and stores those. No experiment processing happens at boot.
    """
    try:
        logger.info("Starting DST Dashboard initialization...")

        config = LoadConfig().WithValidateDatasources()
        logger.info(f"Loaded {len(config.datasources)} datasources from config.yaml")

        app.state.config = config
        app.state.datasources = config.datasources

        db = DSTDatabase()
        db.insert_datasource_list(config.datasources)
        logger.info(f"Stored {len(config.datasources)} datasources")

        logger.info("DST Dashboard initialization completed")

    except Exception as e:
        logger.error(f"Failed to initialize DST Dashboard: {e}", exc_info=True)
        sys.exit(1)


# Enable CORS for the frontend only.
# allow_credentials isn't needed here;
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in str(Constants.DST_ALLOWED_ORIGINS).split(",")],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(admin.router)
app.include_router(experiments.router)
app.include_router(datasources.router)
app.include_router(datasets.router)
app.include_router(panels.router)


@app.get("/")
def root():
    return {
        "service": "DST Dashboard API",
        "version": "0.1.0",
        "docs": "/api/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
