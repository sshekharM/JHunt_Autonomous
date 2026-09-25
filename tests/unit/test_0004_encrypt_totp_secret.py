"""
CHG-005 AC6/AC7: migration 0004 moves the TOTP secret into an encrypted column
and its downgrade restores the plaintext exactly.

The row transforms are checked on their own, and the whole upgrade/downgrade
runs against an in-memory SQLite copy of the two tables, so no PostgreSQL is
needed. tests/integration/test_totp_secret_migration.py repeats the round trip
on PostgreSQL when RUN_DB_TESTS=1.
"""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.fernet import Fernet

from app.security.encryption import decrypt, encrypt

PATH = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0004_encrypt_totp_secret.py"


def _load():
    spec = importlib.util.spec_from_file_location("migration_0004", PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mig = _load()
FERNET = Fernet(Fernet.generate_key())
SECRETS = {"a": "JBSWY3DPEHPK3PXP", "b": "", "c": "KRSXG5CTMVRXEZLU", "d": "ONSWG4TFOQ======"}


def test_revision_chain():
    assert mig.revision == "0004" and mig.down_revision == "0003"
    assert mig.TABLES == ("users", "admin_users")


def test_encrypt_then_decrypt_round_trips_a_secret():
    token = mig.encrypt_secret(FERNET, "JBSWY3DPEHPK3PXP")

    assert isinstance(token, bytes) and b"JBSWY3DPEHPK3PXP" not in token
    assert FERNET.decrypt(token) == b"JBSWY3DPEHPK3PXP"
    assert mig.decrypt_secret(FERNET, token) == "JBSWY3DPEHPK3PXP"


@pytest.mark.parametrize("plain,token", [("", b""), (None, None)])
def test_blank_and_null_secrets_stay_blank_both_ways(plain, token):
    assert mig.encrypt_secret(FERNET, plain) == token
    assert mig.decrypt_secret(FERNET, token) == plain


def test_decrypt_accepts_a_memoryview_from_the_driver():
    token = FERNET.encrypt(b"KRSXG5CTMVRXEZLU")

    assert mig.decrypt_secret(FERNET, memoryview(token)) == "KRSXG5CTMVRXEZLU"


def test_the_migration_uses_the_app_fernet_key():
    token = mig.encrypt_secret(mig.app_fernet(), "JBSWY3DPEHPK3PXP")

    assert decrypt(token) == "JBSWY3DPEHPK3PXP"
    assert mig.decrypt_secret(mig.app_fernet(), encrypt("ONSWG4TF")) == "ONSWG4TF"


def _engine_with(tables=("users", "admin_users"), secrets=SECRETS):
    engine = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    for name in tables:
        sa.Table(name, meta, sa.Column("id", sa.String(36), primary_key=True),
                 sa.Column("totp_secret", sa.String(64), nullable=False),
                 sa.Column("is_active", sa.Boolean, nullable=False))
    meta.create_all(engine)
    with engine.begin() as conn:
        for name in tables:
            conn.execute(sa.table(name, sa.column("id"), sa.column("totp_secret"),
                                  sa.column("is_active")).insert(),
                         [{"id": k, "totp_secret": v, "is_active": True} for k, v in secrets.items()])
    return engine


def _run(engine, step):
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        step()


def _rows(engine, table, column):
    with engine.connect() as conn:
        return dict(conn.execute(sa.text(f"SELECT id, {column} FROM {table}")).all())


def _columns(engine, table):
    return {c["name"]: c for c in sa.inspect(engine).get_columns(table)}


def test_rewrite_column_visits_every_row_in_batches():
    engine = _engine_with(tables=("users",))
    with engine.begin() as conn:
        conn.execute(sa.text("ALTER TABLE users ADD COLUMN totp_secret_encrypted BLOB"))
        seen = []

        def upper(value):
            seen.append(value)
            return value.upper().encode()

        count = mig.rewrite_column(conn, "users", "totp_secret", "totp_secret_encrypted",
                                   upper, batch_size=3)

    assert count == 4 and sorted(seen) == sorted(SECRETS.values())
    assert _rows(engine, "users", "totp_secret_encrypted") == {
        k: v.upper().encode() for k, v in SECRETS.items()}


def test_upgrade_encrypts_every_secret_and_drops_the_plaintext_column():
    engine = _engine_with()
    _run(engine, mig.upgrade)

    for table in mig.TABLES:
        columns = _columns(engine, table)
        assert "totp_secret" not in columns
        assert columns["totp_secret_encrypted"]["nullable"] is False
        stored = _rows(engine, table, "totp_secret_encrypted")
        assert stored["b"] == b""
        assert {k: decrypt(v) for k, v in stored.items() if v} == {
            k: v for k, v in SECRETS.items() if v}


def test_downgrade_restores_the_original_plaintext():
    engine = _engine_with()
    _run(engine, mig.upgrade)
    _run(engine, mig.downgrade)

    for table in mig.TABLES:
        columns = _columns(engine, table)
        assert "totp_secret_encrypted" not in columns
        assert columns["totp_secret"]["nullable"] is False
        assert _rows(engine, table, "totp_secret") == SECRETS
