"""Small presentation-only helpers; no access to codes or session credentials."""
from pathlib import Path
import streamlit as st

_keyboard = st.components.v2.component(
    'project_votes_numeric_keyboard',
    js="""
    export default function() {
        const apply = () => {
            const input = document.querySelector('.st-key-login_code input');
            if (!input) return false;
            input.setAttribute('inputmode', 'numeric');
            input.setAttribute('autocapitalize', 'off');
            input.setAttribute('spellcheck', 'false');
            return true;
        };
        if (apply()) return;
        const observer = new MutationObserver(() => {
            if (apply()) observer.disconnect();
        });
        observer.observe(document.body, {childList: true, subtree: true});
        return () => observer.disconnect();
    }
    """,
)


def apply_layout(logged_in, storage_ready):
    st.html(Path(__file__).parent / 'mobile.css')
    _keyboard(
        key='numeric_login_keyboard', height=0,
        data={'logged_in': logged_in, 'storage_ready': storage_ready},
    )
