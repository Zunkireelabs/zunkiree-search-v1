"""Drift guard: the SQLAlchemy models for visitor_profiles / widget_messages must declare everything
migration 042 creates, so Base.metadata.create_all() on a fresh database cannot produce a subtly weaker
schema. Metadata-only: compiles DDL offline and reads the .sql file. Never connects to a database."""
import re
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.database import Base

MIGRATION = (Path(__file__).resolve().parents[1] / "migrations" / "042_education_agent_memory.sql").read_text()


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


MIGRATION_N = _norm(MIGRATION)
PROFILES = Base.metadata.tables["visitor_profiles"]
MESSAGES = Base.metadata.tables["widget_messages"]

# (table, column) -> (server default as the model declares it, the DEFAULT clause as 042 writes it)
SERVER_DEFAULTS = {
    ("visitor_profiles", "id"): ("gen_random_uuid()", "default gen_random_uuid()"),
    ("visitor_profiles", "profile"): ("'{}'::jsonb", "default '{}'"),
    ("visitor_profiles", "created_at"): ("now()", "default now()"),
    ("visitor_profiles", "updated_at"): ("now()", "default now()"),
    ("widget_messages", "id"): ("gen_random_uuid()", "default gen_random_uuid()"),
    ("widget_messages", "content"): ("''", "default ''"),
    ("widget_messages", "blocks"): ("'[]'::jsonb", "default '[]'"),
    ("widget_messages", "created_at"): ("now()", "default now()"),
}


@pytest.mark.parametrize("table,column", list(SERVER_DEFAULTS), ids=lambda v: str(v))
def test_server_default_matches_migration(table, column):
    declared, in_sql = SERVER_DEFAULTS[(table, column)]
    col = Base.metadata.tables[table].c[column]
    assert col.server_default is not None, f"{table}.{column} has no server_default"
    assert _norm(str(col.server_default.arg)) == _norm(declared)
    assert in_sql in MIGRATION_N, f"042 no longer declares '{in_sql}' (update the models and this test together)"


@pytest.mark.parametrize("table,column", [("visitor_profiles", "email")])
def test_nullable_columns_match_migration(table, column):
    assert Base.metadata.tables[table].c[column].nullable is True


@pytest.mark.parametrize("table,columns", [
    ("visitor_profiles", ["id", "customer_id", "session_id", "profile", "created_at", "updated_at"]),
    ("widget_messages", ["id", "customer_id", "session_id", "role", "content", "blocks", "created_at"]),
])
def test_not_null_columns_match_migration(table, columns):
    t = Base.metadata.tables[table]
    assert [c for c in columns if t.c[c].nullable] == []


def _ddl(index) -> str:
    return _norm(str(CreateIndex(index).compile(dialect=postgresql.dialect())))


def _index(table, name):
    found = [i for i in table.indexes if i.name == name]
    assert len(found) == 1, f"{table.name} must declare index {name}"
    return found[0]


def test_partial_email_index_matches_migration():
    idx = _index(PROFILES, "idx_visitor_profiles_customer_email")
    assert _ddl(idx) == ("create index idx_visitor_profiles_customer_email on visitor_profiles "
                         "(customer_id, lower(email)) where email is not null")
    assert idx.unique is False
    assert "idx_visitor_profiles_customer_email" in MIGRATION_N
    assert "(customer_id, lower(email)) where email is not null" in MIGRATION_N


def test_session_lookup_index_matches_migration():
    idx = _index(MESSAGES, "idx_widget_messages_session")
    assert _ddl(idx) == "create index idx_widget_messages_session on widget_messages (customer_id, session_id, created_at)"
    assert idx.unique is False
    assert "idx_widget_messages_session on widget_messages (customer_id, session_id, created_at)" in MIGRATION_N


def test_models_declare_no_indexes_beyond_the_migration():
    assert {i.name for i in PROFILES.indexes} == {"idx_visitor_profiles_customer_email"}
    assert {i.name for i in MESSAGES.indexes} == {"idx_widget_messages_session"}


def test_unique_constraint_matches_migration():
    uniques = [c for c in PROFILES.constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert [(u.name, [c.name for c in u.columns]) for u in uniques] == [
        ("uq_visitor_profiles_customer_session", ["customer_id", "session_id"])]
    assert "constraint uq_visitor_profiles_customer_session unique (customer_id, session_id)" in MIGRATION_N


@pytest.mark.parametrize("table", [PROFILES, MESSAGES], ids=lambda t: t.name)
def test_customer_foreign_key_cascades(table):
    fks = list(table.foreign_keys)
    assert len(fks) == 1
    fk = fks[0]
    assert fk.parent.name == "customer_id"
    assert fk.column.table.name == "customers" and fk.column.name == "id"
    assert fk.ondelete == "CASCADE"
    assert "references customers(id) on delete cascade" in MIGRATION_N
