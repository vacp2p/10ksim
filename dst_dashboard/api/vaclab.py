"""Vaclab live node topology/resources API routes."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from dst_dashboard.processors.vaclab_processor import VaclabDataUnavailableError

router = APIRouter(prefix="/vaclab", tags=["vaclab"])
logger = logging.getLogger(__name__)


@router.get("/nodes")
def get_vaclab_nodes(request: Request) -> Dict[str, Any]:
    """Live snapshot of vaclab node topology + CPU/RAM/storage/network usage."""
    from dst_dashboard.api.utils import get_vaclab_processor

    processor = get_vaclab_processor(request)
    try:
        return processor.get_snapshot()
    except VaclabDataUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
