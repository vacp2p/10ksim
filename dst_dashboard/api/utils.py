"""Utility functions for API routes."""

import logging

from fastapi import HTTPException, Request

from dst_dashboard.processors.experiment_processor import ExperimentProcessor
from dst_dashboard.processors.panel_processor import PanelProcessor
from dst_dashboard.processors.vaclab_processor import VaclabProcessor
from dst_dashboard.storage.db import DSTDatabase

logger = logging.getLogger(__name__)

VACLAB_DATASOURCE_NAME = "victoria-metrics"


def get_processor(request: Request) -> ExperimentProcessor:
    """Build an ExperimentProcessor from app state (DB is source of truth for experiments)."""
    config = getattr(request.app.state, "config", None)
    if config is None:
        raise HTTPException(status_code=500, detail="Config is not initialized")
    db = DSTDatabase()
    return ExperimentProcessor(config, db)


def get_panel_processor(request: Request) -> PanelProcessor:
    """Build a PanelProcessor from app state."""
    config = getattr(request.app.state, "config", None)
    if config is None:
        raise HTTPException(status_code=500, detail="Config is not initialized")
    db = DSTDatabase()
    return PanelProcessor(config, db)


def get_vaclab_processor(request: Request) -> VaclabProcessor:
    """Build a VaclabProcessor from the configured victoria-metrics datasource."""
    datasources = getattr(request.app.state, "datasources", None)
    if datasources is None:
        raise HTTPException(status_code=500, detail="Datasources are not initialized")
    datasource = next((ds for ds in datasources if ds.name == VACLAB_DATASOURCE_NAME), None)
    if datasource is None:
        raise HTTPException(
            status_code=500, detail=f"'{VACLAB_DATASOURCE_NAME}' datasource not configured"
        )
    return VaclabProcessor(datasource)
