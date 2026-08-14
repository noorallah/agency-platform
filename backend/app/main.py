"""FastAPI application composition root and ASGI entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.dependencies.settings import get_settings
from app.api.routers.dashboard import router as dashboard_router
from app.api.routers.health import router as health_router
from app.batch_serial.api import router as batch_serial_router
from app.branches.api import router as branch_warehouse_router
from app.business.api import router as business_framework_router
from app.common.audit.api import router as audit_logs_router
from app.core.config.settings import Settings
from app.core.database.engine import DatabaseManager
from app.core.exceptions.handlers import register_exception_handlers
from app.core.logging.configuration import configure_logging
from app.core.middleware import CoreRequestMiddleware
from app.core.openapi import OPENAPI_TAGS, build_openapi_metadata
from app.core.tenancy import (
    FirmConnectionResolver,
    FirmRegistryTenantResolver,
    FirmSchemaResolver,
    MultiTenantDatabaseProvider,
    TenantStorageLifecycleService,
)
from app.customers.api import router as customers_router
from app.delivery_note.api import router as delivery_notes_router
from app.diagnostics.api import router as diagnostics_router
from app.document_framework.api import router as document_framework_router
from app.finance.api import router as finance_router
from app.firms.api import router as firms_router
from app.goods_receipt.api import router as goods_receipt_router
from app.identity.api import router as identity_router
from app.inventory.api import router as inventory_router
from app.products.api import router as products_router
from app.purchase.api import router as purchases_router
from app.purchase_invoice.api import router as purchase_invoices_router
from app.purchase_return.api import router as purchase_returns_router
from app.quotation.api import router as quotations_router
from app.sales.api.router import router as sales_territories_router
from app.sales_invoice.api import router as sales_invoices_router
from app.sales_order.api import router as sales_orders_router
from app.sales_return.api import router as sales_returns_router
from app.search.api import router as global_search_router
from app.settlements.api import payments_router, receipts_router, refunds_router
from app.tax.api import router as tax_framework_router
from app.uom.api import router as uom_framework_router
from app.vendors.api import router as vendors_router

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance.

    Args:
        settings: Explicit settings, primarily for isolated application tests.

    Returns:
        A fully configured FastAPI application.

    """
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Manage application-level startup and shutdown hooks."""
        logger.info(
            "Application startup: name=%s environment=%s",
            settings.app_name,
            settings.environment,
        )
        try:
            yield
        finally:
            application.state.database_provider.dispose()
            application.state.database.dispose()
            logger.info("Application shutdown: name=%s", settings.app_name)

    application = FastAPI(
        **build_openapi_metadata(settings),
        debug=settings.debug,
        lifespan=lifespan,
        openapi_tags=OPENAPI_TAGS,
    )
    application.state.settings = settings
    application.state.database = DatabaseManager.from_settings(settings)
    application.state.tenant_resolver = FirmRegistryTenantResolver(
        application.state.database,
        shared_database_name=settings.tenancy.shared_database_name,
        shared_schema_name=settings.tenancy.shared_schema_name,
    )
    application.state.database_provider = MultiTenantDatabaseProvider(
        application.state.database,
        FirmConnectionResolver(
            application.state.database, settings.tenancy.connection_profiles
        ),
        FirmSchemaResolver(),
    )
    application.state.tenant_storage_lifecycle = TenantStorageLifecycleService(
        application.state.database,
        settings.tenancy.connection_profiles,
    )
    application.add_middleware(CoreRequestMiddleware)
    application.include_router(health_router)
    application.include_router(dashboard_router)
    application.include_router(identity_router)
    application.include_router(firms_router)
    application.include_router(customers_router)
    application.include_router(products_router)
    application.include_router(purchases_router)
    application.include_router(purchase_invoices_router)
    application.include_router(purchase_returns_router)
    application.include_router(sales_invoices_router)
    application.include_router(sales_returns_router)
    application.include_router(sales_orders_router)
    application.include_router(quotations_router)
    application.include_router(delivery_notes_router)
    application.include_router(goods_receipt_router)
    application.include_router(vendors_router)
    application.include_router(branch_warehouse_router)
    application.include_router(sales_territories_router)
    application.include_router(global_search_router)
    application.include_router(tax_framework_router)
    application.include_router(business_framework_router)
    application.include_router(inventory_router)
    application.include_router(batch_serial_router)
    application.include_router(document_framework_router)
    application.include_router(uom_framework_router)
    application.include_router(finance_router)
    application.include_router(receipts_router)
    application.include_router(payments_router)
    application.include_router(refunds_router)
    application.include_router(audit_logs_router)
    application.include_router(diagnostics_router)
    register_exception_handlers(application)
    return application


def create_application() -> FastAPI:
    """Create an application using the legacy factory name.

    Returns:
        A fully configured FastAPI application.

    """
    return create_app()


app = create_app()
