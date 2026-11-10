"""Streamlit V2 bridge to browser storage, with acknowledged, one-shot operations."""
from pathlib import Path
import secrets

import streamlit as st

_storage = st.components.v2.component(
    'project_votes_student_storage',
    js=(Path(__file__).parent / 'session_storage.js').read_text(encoding='utf-8'),
)


def _operation(action, **values):
    st.session_state['_student_storage_op'] = dict(id=secrets.token_hex(16), action=action, **values)


def remember(token, expires_at):
    st.session_state['_student_token'] = token
    st.session_state['_student_storage_loaded'] = True
    _operation('set', token=token, expires_at=expires_at)


def forget():
    st.session_state.pop('_student_token', None)
    _operation('clear')


def sync():
    if '_student_storage_op' not in st.session_state:
        _operation('read')
    op = st.session_state['_student_storage_op']
    result = _storage(
        key='student_browser_storage', height=0,
        data=dict(op, acknowledged=st.session_state.get('_student_storage_ack') == op['id']),
        on_event_change=lambda: None,
    )
    event = result.event
    if isinstance(event, dict) and event.get('id') == op['id'] and st.session_state.get('_student_storage_ack') != op['id']:
        st.session_state['_student_storage_ack'] = op['id']
        st.session_state['_student_storage_ok'] = bool(event.get('ok'))
        if op['action'] == 'read':
            # Treat browser input as untrusted: server-side validation follows.
            st.session_state['_student_token'] = event.get('token')
            st.session_state['_student_storage_loaded'] = True
    return (
        st.session_state.get('_student_storage_loaded', False),
        st.session_state.get('_student_token'),
        st.session_state.get('_student_storage_ok', True),
    )
