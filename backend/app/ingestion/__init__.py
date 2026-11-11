"""Controlled synthetic text imports; no HTTP routes or live source adapters."""

from app.ingestion.service import import_synthetic_batch

__all__ = ["import_synthetic_batch"]
