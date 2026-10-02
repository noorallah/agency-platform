"""Customer, supplier and product codes issued from a series (MST-5, A67).

A code was typed by hand on every new customer, supplier and product, which is
a chore for a counter clerk and is how ``C1``, ``CUST1`` and ``CUST-001`` end
up in the same firm. Each master now has a series in the document framework,
as stock movements do (``movement_numbering.py``): leave the code blank and
the next one is issued -- ``CUS-00001``, ``SUP-00001``, ``PRD-00001`` -- or type
one, as an import or a firm keeping its old codes does. The series has no
financial year and never restarts, since a code is the record's name for good;
a firm changes the prefix or padding under Settings > Numbering like any other.
"""

from uuid import UUID

from sqlalchemy.orm import InstrumentedAttribute, Session

from app.core.utils.dates import utc_now
from app.document_framework.services.transactional_document_service import (
    DocumentStateSpec,
    DocumentTypeSpec,
    TransactionalDocumentService,
)

_ACTIVE = (DocumentStateSpec("ACTIVE", "Active", 1, is_terminal=True),)

#: One series per master, keyed by the master the service asks for.
MASTER_SERIES: dict[str, DocumentTypeSpec] = {
    master: DocumentTypeSpec(
        code=code,
        name=name,
        description=f"{name}s issued when the code is left blank",
        category="MASTER",
        module=module,
        prefix=prefix,
        states=_ACTIVE,
        sequence_padding=5,
        yearly=False,
    )
    for master, code, name, module, prefix in (
        ("CUSTOMER", "CUSTOMER_CODE", "Customer Code", "customers", "CUS"),
        ("VENDOR", "VENDOR_CODE", "Supplier Code", "vendors", "SUP"),
        ("PRODUCT", "PRODUCT_CODE", "Product Code", "products", "PRD"),
    )
}


class MasterCodeNumbering(TransactionalDocumentService):
    """Issue the next code of one master's series, inside the caller's work.

    Reserves under the series row's lock and flushes; it never commits, so a
    record refused afterwards takes its code back with it.
    """

    def __init__(self, session: Session, master: str) -> None:
        """Bind the series for ``master`` (a key of ``MASTER_SERIES``)."""
        super().__init__(session)
        self.DOCUMENT = MASTER_SERIES[master]

    def code(
        self,
        typed: str | None,
        *,
        code_column: InstrumentedAttribute[str],
        firm_id: UUID,
        actor_id: UUID,
    ) -> str:
        """Return the typed code, or the series' next one when none was typed.

        A code the series would have issued is stepped over, as a document
        number is, so a hand-typed ``CUS-00007`` never collides with the
        counter reaching seven.
        """
        if typed is not None and typed.strip():
            return typed.strip().upper()
        _, rule = self._ensure_document_setup(firm_id=firm_id, actor_id=actor_id)
        return self._issue_number(
            rule,
            typed=None,
            number_column=code_column,
            firm_id=firm_id,
            document_date=utc_now().date(),
            actor_id=actor_id,
            company_code=self._company_code(firm_id),
        )
