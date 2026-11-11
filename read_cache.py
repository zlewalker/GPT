"""Short, server-side cache for public aggregates only. Never cache authentication."""

import hashlib

import streamlit as st

import database as db

CACHE_SECONDS = 10


def _database_scope():
    # Isolate databases without putting a connection string in cache arguments/logs.
    if db.postgres.enabled():
        identity = db.postgres.setting('DATABASE_URL') + '\0' + db.postgres.schema_name()
    else:
        identity = str(db.DB_PATH.resolve())
    return hashlib.sha256(identity.encode('utf-8')).hexdigest()


@st.cache_data(ttl=CACHE_SECONDS, max_entries=32, show_spinner=False)
def _stats(database_scope):
    return db.teacher_stats()


@st.cache_data(ttl=CACHE_SECONDS, max_entries=32, show_spinner=False)
def _teachers(database_scope):
    return db.list_teachers()


@st.cache_data(ttl=CACHE_SECONDS, max_entries=128, show_spinner=False)
def _history(database_scope, subject, min_votes):
    return db.subject_history(subject, min_votes)


def teacher_stats():
    return _stats(_database_scope())


def list_teachers():
    return _teachers(_database_scope())


def subject_history(subject, min_votes=3):
    return _history(_database_scope(), subject, min_votes)


def clear():
    """Call after a committed write or explicit refresh, never before commit."""
    _stats.clear()
    _teachers.clear()
    _history.clear()
