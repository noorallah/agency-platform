"""Customer API contracts."""

from app.customers.schemas.customer import (
    CustomerAddressInput,
    CustomerAddressResponse,
    CustomerContactInput,
    CustomerContactResponse,
    CustomerCreate,
    CustomerImportRequest,
    CustomerResponse,
    CustomerSummary,
    CustomerUpdate,
)

__all__ = [
    "CustomerAddressInput",
    "CustomerAddressResponse",
    "CustomerContactInput",
    "CustomerContactResponse",
    "CustomerCreate",
    "CustomerImportRequest",
    "CustomerResponse",
    "CustomerSummary",
    "CustomerUpdate",
]
