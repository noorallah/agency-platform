"""A dedicated store's placeholder salesmen are named from the platform's users.

The migration that builds the salesman list (`20261014_0380`) gives every id
the salesman columns hold an entry of its own. Where it cannot read
``platform.users`` -- a firm in a database of its own -- the entry is named
``Salesman`` and the first eight characters of the id, and
``upgrade_every_store`` renames it once every store is at head, through
``rename_placeholder_salesmen`` on the firm's own connection.

Only a real schema of its own shows the helper reaching the store it was
pointed at and no other; the unit suite has one SQLite schema.
"""

from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from app.core.tenancy.migrations import rename_placeholder_salesmen
from app.salesmen.naming import placeholder_name


def _entry(
    engine: Engine, schema: str, firm_id: UUID, user_id: UUID, name: str
) -> UUID:
    """Insert one live entry into the schema and return its id."""
    entry_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                f'INSERT INTO "{schema}".salesmen '
                "(id, firm_id, name, user_id, earns_commission, is_active, "
                "is_deleted, version) "
                "VALUES (:id, :firm, :name, :user, true, true, false, 1)"
            ),
            {"id": entry_id, "firm": firm_id, "name": name, "user": user_id},
        )
    return entry_id


def _names(engine: Engine, schema: str) -> dict[UUID, str]:
    """Read every entry's name from the schema."""
    with engine.connect() as connection:
        return {
            UUID(str(row_id)): name
            for row_id, name in connection.execute(
                text(f'SELECT id, name FROM "{schema}".salesmen')
            ).all()
        }


def test_placeholders_are_renamed_and_typed_names_are_left(
    engine: Engine, temp_schema: str
) -> None:
    """The placeholder takes the user's name; a clash takes the id's eight."""
    firm = uuid4()
    mohan, second_mohan, typed, unknown = uuid4(), uuid4(), uuid4(), uuid4()
    first = _entry(engine, temp_schema, firm, mohan, placeholder_name(mohan))
    second = _entry(
        engine, temp_schema, firm, second_mohan, placeholder_name(second_mohan)
    )
    kept = _entry(engine, temp_schema, firm, typed, "Ravi on the north beat")
    left = _entry(engine, temp_schema, firm, unknown, placeholder_name(unknown))

    renamed = rename_placeholder_salesmen(
        database_url=engine.url.render_as_string(hide_password=False),
        schema_name=temp_schema,
        user_names={mohan: "Mohan", second_mohan: "Mohan", typed: "Ravi"},
    )

    names = _names(engine, temp_schema)
    assert renamed == 2
    pair = {first: mohan, second: second_mohan}
    plain = [entry for entry in pair if names[entry] == "Mohan"]
    assert len(plain) == 1
    other = next(entry for entry in pair if entry not in plain)
    assert names[other] == f"Mohan {str(pair[other])[:8]}"
    assert names[kept] == "Ravi on the north beat"
    assert names[left] == placeholder_name(unknown)

    # A replay finds nothing left to do.
    assert (
        rename_placeholder_salesmen(
            database_url=engine.url.render_as_string(hide_password=False),
            schema_name=temp_schema,
            user_names={mohan: "Mohan", second_mohan: "Mohan", typed: "Ravi"},
        )
        == 0
    )


def test_a_store_without_the_list_is_left_alone(
    engine: Engine, temp_schema: str
) -> None:
    """A store not yet holding ``salesmen`` answers nothing renamed."""
    with engine.begin() as connection:
        # CASCADE: every salesman column holds a key to it (`20261014_0382`).
        connection.execute(text(f'DROP TABLE "{temp_schema}".salesmen CASCADE'))

    assert (
        rename_placeholder_salesmen(
            database_url=engine.url.render_as_string(hide_password=False),
            schema_name=temp_schema,
            user_names={uuid4(): "Mohan"},
        )
        == 0
    )
