"""Small PostgreSQL adapter for the application's parameterized SQL."""

import atexit
from contextlib import contextmanager
import os
from pathlib import Path
import re
import tomllib
from threading import Lock


_pool = None
_pool_key = None
_pool_lock = Lock()


def setting(name, default=''):
    if name in os.environ:
        return os.environ[name]
    path = Path(__file__).parent / '.streamlit' / 'secrets.toml'
    if path.exists():
        with path.open('rb') as file:
            values = tomllib.load(file)
        if name in values:
            return values[name]
    # Community Cloud manages secrets outside the repository. Accessing st.secrets
    # also initializes its root-level environment variables on the first read.
    try:
        import streamlit as st
        return st.secrets.get(name, default)
    except (ImportError, FileNotFoundError):
        pass
    return default


def enabled():
    return bool(setting('DATABASE_URL'))


def schema_name():
    name = setting('DATABASE_SCHEMA', 'votes_app')
    if name != 'votes_app' and not re.fullmatch(r'votes_test_[a-z0-9_]+', name):
        raise ValueError('DATABASE_SCHEMA deve essere votes_app o votes_test_*.')
    return name


class Record:
    """Support both sqlite3.Row access patterns used by the application."""

    def __init__(self, columns, values):
        self.columns, self.values = columns, values

    def keys(self):
        return self.columns

    def __getitem__(self, key):
        return self.values[key if isinstance(key, int) else self.columns.index(key)]

    def __iter__(self):
        return iter(self.values)


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor
        self.rowcount = cursor.rowcount

    def _row(self, row):
        return None if row is None else Record([c.name for c in self.cursor.description], row)

    def fetchone(self):
        return self._row(self.cursor.fetchone())

    def fetchall(self):
        return [self._row(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class Connection:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, query, params=()):
        # Only application-owned SQL is passed here. Values always stay bound.
        query = query.replace('%', '%%').replace('?', '%s')
        return Cursor(self.raw.execute(query, params))


def close_pool():
    """Release idle connections; active borrowers finish their transactions."""
    global _pool, _pool_key
    with _pool_lock:
        if _pool is not None:
            _pool.close()
        _pool = _pool_key = None


atexit.register(close_pool)


def _get_pool(options):
    from psycopg_pool import ConnectionPool
    global _pool, _pool_key
    key = tuple(sorted(options.items()))
    with _pool_lock:
        if _pool is None or _pool_key != key:
            if _pool is not None:
                _pool.close()
            _pool = ConnectionPool(
                conninfo='', kwargs=dict(options, prepare_threshold=None),
                min_size=0, max_size=4, max_idle=60, max_lifetime=600,
                timeout=10, check=ConnectionPool.check_connection, open=True,
            )
            _pool_key = key
        return _pool


@contextmanager
def connect():
    try:
        import psycopg
    except ImportError:
        raise RuntimeError('Installa requirements.txt per usare PostgreSQL.') from None
    from psycopg.conninfo import conninfo_to_dict
    options = conninfo_to_dict(setting('DATABASE_URL'))
    if options.get('sslmode', 'require') not in ('require', 'verify-ca', 'verify-full'):
        raise ValueError('La connessione PostgreSQL richiede TLS (sslmode=require).')
    options.setdefault('sslmode', 'require')
    options.setdefault('connect_timeout', '10')
    # Keep the same transaction boundary in both modes. Never share an active
    # connection between sessions, and never retry writes after a network error.
    use_pool = str(setting('DATABASE_POOL_ENABLED', '1')).strip().lower() not in ('0', 'false', 'no')
    manager = (_get_pool(options).connection() if use_pool
               else psycopg.connect(**options, prepare_threshold=None))
    with manager as raw:
        # Transaction-local settings cannot leak to the next borrower or schema.
        # One round trip instead of three; schema_name() validates the identifier.
        raw.execute(
            f'SET LOCAL search_path TO "{schema_name()}", pg_catalog; '
            "SET LOCAL statement_timeout = '20s'; "
            "SET LOCAL lock_timeout = '15s'"
        )
        yield Connection(raw)


def begin_write(con):
    # Transaction-scoped lock, shared by all writers, released on commit/rollback.
    # A class-sized app benefits from SQLite-like serialization of short writes.
    con.execute('SELECT pg_advisory_xact_lock(hashtext(current_schema()), 1)')


def check_ready():
    with connect() as con:
        values = dict(con.execute('SELECT key, value FROM settings').fetchall())
        if values.get('schema_version') != '1':
            raise RuntimeError('Schema PostgreSQL non inizializzato o versione non supportata.')
        if values.get('migration_ready') != '1' or not values.get('voter_key'):
            raise RuntimeError('Completa e verifica la migrazione prima di avviare l’app online.')
        if values.get('school_year') != '2026/2027':
            raise RuntimeError('Anno scolastico del database non supportato.')
