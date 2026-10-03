"""FastAPI application composition root and ASGI entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.dependencies.settings import get_settings
from app.api.routers.dashboard import router as dashboard_router
from app.api.routers.health import router as health_router
from app.approvals.api import router as approvals_router
from app.backups.api import router as backups_router
from app.bank_reconciliation.api.router import router as bank_reconciliation_router
from app.batch_serial.api import router as batch_serial_router
from app.branches.api import router as branch_warehouse_router
from app.business.api import router as business_framework_router
from app.commission.api import router as commission_router
from app.common.audit.api import router as audit_logs_router
from app.common.directory.api import router as firm_members_router
from app.contra.api.router import router as contra_router
from app.core.config.settings import Settings
from app.core.database.engine import DatabaseManager
from app.core.exceptions.handlers import register_exception_handlers
from app.core.logging.configuration import configure_logging
from app.core.logging.retention import LogMaintenance
from app.core.middleware import CoreRequestMiddleware
from app.core.openapi import OPENAPI_TAGS, build_openapi_metadata
from app.core.tenancy import (
    FirmConnectionResolver,
    FirmRegistryTenantResolver,
    FirmSchemaResolver,
    MultiTenantDatabaseProvider,
    TenantStorageLifecycleService,
)
from app.credit_note.api.router import router as credit_notes_router
from app.customer_debit_note.api.router import router as customer_debit_notes_router
from app.customers.api import router as customers_router
from app.debit_note.api.router import router as debit_notes_router
from app.delivery_note.api import router as delivery_notes_router
from app.diagnostics.api import router as diagnostics_router
from app.document_framework.api import router as document_framework_router
from app.einvoice.api.router import router as einvoice_router
from app.enquiry.api import router as enquiry_router
from app.expenses.api.router import router as expenses_router
from app.finance.api import router as finance_router
from app.firms.api import router as firms_router
from app.goods_receipt.api import router as goods_receipt_router
from app.gst_returns.api.router import router as gst_returns_router
from app.identity.api import router as identity_router
from app.imports.api import router as imports_router
from app.inventory.api import router as inventory_router
from app.landed_costs.api import router as landed_costs_router
from app.loyalty.api import router as loyalty_router
from app.messaging.api import router as messaging_router
from app.messaging.services.outbox_worker import MessagingWorker
from app.messaging.services.runtime import live_firm_ids, store_opener
from app.notifications.api import router as notifications_router
from app.party_adjustments.api.router import router as party_adjustments_router
from app.pricing.api import router as pricing_router
from app.pricing.api.price_levels_router import router as price_levels_router
from app.principal_claims.api import router as principal_claims_router
from app.products.api import router as products_router
from app.proforma.api import router as proforma_router
from app.promotions.api import router as promotions_router
from app.purchase.api import router as purchases_router
from app.purchase_invoice.api import router as purchase_invoices_router
from app.purchase_return.api import router as purchase_returns_router
from app.quotation.api import router as quotations_router
from app.report_layouts.api import router as report_layouts_router
from app.sales.api.router import router as sales_territories_router
from app.sales_invoice.api import router as sales_invoices_router
from app.sales_order.api import router as sales_orders_router
from app.sales_return.api import router as sales_returns_router
from app.sales_targets.api import router as sales_targets_router
from app.search.api import router as global_search_router
from app.settlements.api import payments_router, receipts_router, refunds_router
from app.settlements.api.payment_runs_router import payment_runs_router
from app.settlements.api.post_dated_cheques_router import (
    issued_cheques_router,
    received_cheques_router,
)
from app.supplier_rebates.api import router as supplier_rebates_router
from app.tax.api import router as tax_framework_router
from app.tcs.api import router as tcs_router
from app.trade_licences.api import router as trade_licences_router
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
        # Compress, expire and cap the log folder now and hourly. Only when
        # this process writes log files: otherwise the folder is not ours.
        maintenance = LogMaintenance(settings) if settings.log_file_enabled else None
        if maintenance is not None:
            maintenance.start()
        # Sends what firms queued, retries, and scans for reminders. Started
        # here rather than at import, so a test client that never enters the
        # lifespan never starts a thread.
        messaging = (
            _messaging_worker(application, settings)
            if settings.messaging_worker_enabled
            else None
        )
        if messaging is not None:
            messaging.start()
        try:
            yield
        finally:
            if messaging is not None:
                messaging.stop()
            if maintenance is not None:
                maintenance.stop()
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
        shared_database_name=settings.tenancy.shared_database_name,
        shared_schema_name=settings.tenancy.shared_schema_name,
    )
    application.add_middleware(CoreRequestMiddleware)
    application.include_router(health_router)
    application.include_router(dashboard_router)
    application.include_router(identity_router)
    application.include_router(firms_router)
    application.include_router(customers_router)
    application.include_router(pricing_router)
    application.include_router(price_levels_router)
    application.include_router(promotions_router)
    application.include_router(sales_targets_router)
    application.include_router(report_layouts_router)
    application.include_router(supplier_rebates_router)
    application.include_router(principal_claims_router)
    application.include_router(landed_costs_router)
    application.include_router(approvals_router)
    application.include_router(enquiry_router)
    application.include_router(notifications_router)
    application.include_router(trade_licences_router)
    application.include_router(products_router)
    application.include_router(proforma_router)
    application.include_router(loyalty_router)
    application.include_router(purchases_router)
    application.include_router(purchase_invoices_router)
    application.include_router(purchase_returns_router)
    application.include_router(sales_invoices_router)
    application.include_router(sales_returns_router)
    application.include_router(credit_notes_router)
    application.include_router(customer_debit_notes_router)
    application.include_router(debit_notes_router)
    application.include_router(party_adjustments_router)
    application.include_router(contra_router)
    application.include_router(bank_reconciliation_router)
    application.include_router(einvoice_router)
    application.include_router(gst_returns_router)
    application.include_router(sales_orders_router)
    application.include_router(quotations_router)
    application.include_router(delivery_notes_router)
    application.include_router(goods_receipt_router)
    application.include_router(vendors_router)
    application.include_router(branch_warehouse_router)
    application.include_router(sales_territories_router)
    application.include_router(global_search_router)
    application.include_router(tax_framework_router)
    application.include_router(tcs_router)
    application.include_router(business_framework_router)
    application.include_router(inventory_router)
    application.include_router(batch_serial_router)
    application.include_router(document_framework_router)
    application.include_router(uom_framework_router)
    application.include_router(finance_router)
    application.include_router(receipts_router)
    application.include_router(payments_router)
    application.include_router(received_cheques_router)
    application.include_router(issued_cheques_router)
    application.include_router(payment_runs_router)
    application.include_router(refunds_router)
    application.include_router(expenses_router)
    application.include_router(commission_router)
    application.include_router(audit_logs_router)
    application.include_router(firm_members_router)
    application.include_router(diagnostics_router)
    application.include_router(messaging_router)
    application.include_router(backups_router)
    application.include_router(imports_router)
    register_exception_handlers(application)
    return application


def _messaging_worker(application: FastAPI, settings: Settings) -> MessagingWorker:
    """Build the outbox worker from the tenancy services this app holds."""
    return MessagingWorker(
        live_firm_ids(application.state.database),
        store_opener(
            application.state.tenant_resolver, application.state.database_provider
        ),
        interval_seconds=settings.messaging_worker_interval_seconds,
    )


def create_application() -> FastAPI:
    """Create an application using the legacy factory name.

    Returns:
        A fully configured FastAPI application.

    """
    return create_app()


app = create_app()
