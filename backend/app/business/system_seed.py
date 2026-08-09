"""Baseline business profile seed data for distributor-focused deployments."""

from typing import TypedDict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.business.models import BusinessProfile


class BusinessProfileSeed(TypedDict):
    """One baseline business profile to seed."""

    id: UUID
    code: str
    name: str
    description: str
    industry_type: str
    is_default: bool
    default_settings: dict[str, object]


SEED_BUSINESS_PROFILES: tuple[BusinessProfileSeed, ...] = (
    {
        "id": UUID("10000000-0000-0000-0000-000000000001"),
        "code": "GENERIC",
        "name": "Generic Business",
        "description": "Fallback profile for mixed or not-yet-classified businesses.",
        "industry_type": "GENERIC",
        "is_default": True,
        "default_settings": {
            "business_model": "general",
            "inventory_tracking": "item",
            "batch_required": False,
            "expiry_required": False,
            "retailer_pricing": True,
        },
    },
    {
        "id": UUID("10000000-0000-0000-0000-000000000002"),
        "code": "AGENCY",
        "name": "General Agency Distribution",
        "description": "Standard B2B distributor profile for agencies supplying shops.",
        "industry_type": "AGENCY",
        "is_default": False,
        "default_settings": {
            "business_model": "distributor",
            "inventory_tracking": "item",
            "batch_required": False,
            "expiry_required": False,
            "salesman_tracking": True,
            "route_management": True,
            "retailer_pricing": True,
            "credit_sales": True,
        },
    },
    {
        "id": UUID("10000000-0000-0000-0000-000000000003"),
        "code": "PHARMACY",
        "name": "Pharma Distribution",
        "description": "Distributor profile for medicine and healthcare products.",
        "industry_type": "PHARMACY",
        "is_default": False,
        "default_settings": {
            "business_model": "distributor",
            "inventory_tracking": "batch",
            "batch_required": True,
            "expiry_required": True,
            "mrp_control": True,
            "ptr_support": True,
            "sale_return_window_days": 30,
            "compliance_mode": "pharma",
        },
    },
    {
        "id": UUID("10000000-0000-0000-0000-000000000004"),
        "code": "FOOD",
        "name": "Food Distribution",
        "description": "Distributor profile for food, grocery, and packaged goods.",
        "industry_type": "FOOD",
        "is_default": False,
        "default_settings": {
            "business_model": "distributor",
            "inventory_tracking": "batch",
            "batch_required": True,
            "expiry_required": True,
            "near_expiry_alert_days": 30,
            "damaged_returns": True,
            "cold_storage": False,
        },
    },
    {
        "id": UUID("10000000-0000-0000-0000-00000000000A"),
        "code": "WHOLESALE",
        "name": "Wholesale Distribution",
        "description": (
            "Bulk B2B distribution profile for wholesale and cash-and-carry flows."
        ),
        "industry_type": "WHOLESALE",
        "is_default": False,
        "default_settings": {
            "business_model": "wholesale",
            "inventory_tracking": "item",
            "batch_required": False,
            "expiry_required": False,
            "counter_sales": True,
            "bulk_pricing": True,
            "credit_sales": True,
        },
    },
)


def seed_business_profiles(session: Session) -> None:
    """Create or restore baseline business profiles without touching custom rows."""
    existing = {
        profile.code: profile for profile in session.scalars(select(BusinessProfile))
    }
    for seed in SEED_BUSINESS_PROFILES:
        profile = existing.get(seed["code"])
        if profile is None:
            session.add(
                BusinessProfile(
                    id=seed["id"],
                    code=seed["code"],
                    name=seed["name"],
                    description=seed["description"],
                    industry_type=seed["industry_type"],
                    status="ACTIVE",
                    is_default=bool(seed["is_default"]),
                    default_settings=dict(seed["default_settings"]),
                )
            )
            continue
        profile.name = str(seed["name"])
        profile.description = str(seed["description"])
        profile.industry_type = str(seed["industry_type"])
        profile.status = "ACTIVE"
        profile.is_default = bool(seed["is_default"])
        profile.default_settings = dict(seed["default_settings"])
        profile.is_deleted = False
        profile.deleted_at = None
        profile.deleted_by = None
