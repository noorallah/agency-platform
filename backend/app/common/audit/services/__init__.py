"""Audit service exports."""

from app.common.audit.services.audit import record_audit

__all__ = ["record_audit"]
