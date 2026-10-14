"""The firm's own list of salesmen (P2, step 1 of the salesman list design).

A salesman was a user until now: every column that names one holds a user id,
and the people who take an order by phone, or are paid on commission without
ever signing in, could not be named at all. The list is the firm's own -- an
entry may be tied to the account its holder signs in with, or to none.

**An entry made for a user takes that user's id as its own**, which is how the
migration moves the existing columns across without rewriting a document row
(`docs/design/SALESMAN_LIST_DESIGN.md`, section 4).
"""

from uuid import UUID

from sqlalchemy import Boolean, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.entity import BaseEntity
from app.core.database.types import UUIDType


class Salesman(BaseEntity):
    """One entry of the firm's salesman list."""

    __tablename__ = "salesmen"
    __table_args__ = (
        Index(
            "UQ_salesmen_firm_code_active",
            "firm_id",
            "code",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
            sqlite_where=text("NOT is_deleted"),
        ),
        Index(
            "UQ_salesmen_firm_user_active",
            "firm_id",
            "user_id",
            unique=True,
            postgresql_where=text("NOT is_deleted"),
            sqlite_where=text("NOT is_deleted"),
        ),
    )

    #: No foreign key: `firms` lives only in the platform schema.
    firm_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False, index=True)
    #: The firm's own short code, as the old software's salesman master keeps.
    code: Mapped[str | None] = mapped_column(String(30))
    #: What prints. Unique among the firm's live entries, case-insensitive.
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: The account he signs in with. No foreign key: `users` is a platform
    #: table. One user is one salesman.
    user_id: Mapped[UUID | None] = mapped_column(UUIDType())
    phone: Mapped[str | None] = mapped_column(String(20))
    #: False for *Phone order* or *Company staff*: nothing pays it commission.
    earns_commission: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    #: An inactive entry stays on old documents and is offered on none.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    notes: Mapped[str | None] = mapped_column(Text)


#: Declared beside the class because it indexes an expression of a column.
Index(
    "UQ_salesmen_firm_name_active",
    Salesman.firm_id,
    func.lower(Salesman.name),
    unique=True,
    postgresql_where=text("NOT is_deleted"),
    sqlite_where=text("NOT is_deleted"),
)
