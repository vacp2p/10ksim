from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys
import logging

from dst_dashboard.api import admin, datasets, datasources, experiments, panels
from dst_dashboard.api.utils import process_experiments
from dst_dashboard.config.utils import LoadConfig
from dst_dashboard.config.data_structures import ExperimentConfig
from dst_dashboard.storage.db import DSTDatabase
from dst_dashboard.processors.experiment_processor import ExperimentProcessor

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
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
    
    Workflow:
    1. Load config.yaml (datasources + experiments)
    2. Store datasources in database
    3. Process config.yaml experiments (config takes precedence, overwrites DB)
    4. Process DB-only experiments (not in config.yaml)
    5. Only reprocess experiments missing data (datasets or panels)
    """
    try:
        logger.info("Starting DST Dashboard initialization...")
        
        config = LoadConfig().WithValidateDatasources()
        logger.info(
            f"Loaded {len(config.datasources)} datasources and "
            f"{len(config.experiments)} experiments from config.yaml"
        )
        
        app.state.config = config
        app.state.datasources = config.datasources
        
        db = DSTDatabase()
        db.insert_datasource_list(config.datasources)
        logger.info(f"Stored {len(config.datasources)} datasources")
        
        processor = ExperimentProcessor(config, db)
        
        # Phase 1: Process config.yaml experiments
        logger.info("Phase 1: Processing experiments from config.yaml...")
        config_ids = set()
        phase1_stats = process_experiments(
            experiments=config.experiments,
            db=db,
            processor=processor,
            experiment_ids_tracker=config_ids,
            max_workers=1  # Sequential - SQLite has issues with parallel experiment creation
        )
        logger.info(
            f"Phase 1 completed: {phase1_stats['processed']} processed, "
            f"{phase1_stats['failed']} failed"
        )
        
        # Phase 2: Process DB-only experiments
        logger.info("Phase 2: Processing DB-only experiments...")
        db_experiments = [
            ExperimentConfig(**exp_data) 
            for exp_data in db.list_experiments() 
            if exp_data.get("id") not in config_ids
        ]
        phase2_stats = process_experiments(
            experiments=db_experiments,
            db=db,
            processor=processor
        )
        logger.info(
            f"Phase 2 completed: {phase2_stats['processed']} processed, "
            f"{phase2_stats['failed']} failed"
        )
        
        # Summary
        total_processed = phase1_stats['processed'] + phase2_stats['processed']
        total_failed = phase1_stats['failed'] + phase2_stats['failed']
        logger.info(
            f"Initialization completed: {total_processed} experiments processed, "
            f"{total_failed} failed"
        )
        
        if phase1_stats['failed_list']:
            logger.warning(
                f"Failed experiments: {[e['title'] for e in phase1_stats['failed_list']]}"
            )
        
    except Exception as e:
        logger.error(f"Failed to initialize DST Dashboard: {e}", exc_info=True)
        sys.exit(1)


# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
async def root():
    return {
        "service": "DST Dashboard API",
        "version": "0.1.0",
        "docs": "/api/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
