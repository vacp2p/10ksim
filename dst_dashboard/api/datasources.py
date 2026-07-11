"""Datasource API routes."""

from typing import List
from fastapi import APIRouter, HTTPException, Request
from dst_dashboard.config.data_structures import DataSourceConfig
router = APIRouter(prefix="/datasources", tags=["datasources"])


@router.get("", response_model=List[DataSourceConfig])
def list_datasources(
    request: Request,
):
    """List loaded datasources"""
    datasources = getattr(request.app.state, "datasources", None)
    if datasources is None:
        raise HTTPException(status_code=500, detail="Datasources are not initialized")
    return datasources

@router.get("/prometheus", response_model=List[DataSourceConfig])
def list_prometheus_datasources(
    request: Request,
):
    """List prometheus datasources"""
    datasources = getattr(request.app.state, "datasources", None)
    if datasources is None:
        raise HTTPException(status_code=500, detail="Datasources are not initialized")
    prometheus_datasources = [ds for ds in datasources if ds.type.lower() == "prometheus"]
    return prometheus_datasources

@router.get("/victorialogs", response_model=List[DataSourceConfig])
def list_victorialogs_datasources(
    request: Request,
):
    """List victorialogs datasources"""
    datasources = getattr(request.app.state, "datasources", None)
    if datasources is None:
        raise HTTPException(status_code=500, detail="Datasources are not initialized")
    victorialogs_datasources = [ds for ds in datasources if ds.type.lower() == "victorialogs"]
    return victorialogs_datasources

@router.get("/{datasource_name}", response_model=DataSourceConfig)
def get_datasource(datasource_name: str, request: Request):
    """Get a datasource by name from config."""
    datasources = getattr(request.app.state, "datasources", None)
    if datasources is None:
        raise HTTPException(status_code=500, detail="Datasources are not initialized")

    for datasource in datasources:
        if datasource.name == datasource_name:
            return datasource

    raise HTTPException(status_code=404, detail="Datasource not found")
