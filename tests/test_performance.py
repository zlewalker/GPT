"""UI regressions and bounded database work; use temporary data only."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import database as db
import browser_session
import read_cache
import streamlit as st
from streamlit.testing.v1 import AppTest


class PageLoadingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        backend = patch.object(db.postgres, 'enabled', return_value=False)
        backend.start()
        self.addCleanup(backend.stop)
        path = patch.object(db, 'DB_PATH', Path(self.temp.name) / 'votes.sqlite3')
        path.start()
        self.addCleanup(path.stop)
        environment = patch.dict(os.environ, {'ADMIN_PIN': 'test-only-pin'})
        environment.start()
        self.addCleanup(environment.stop)
        storage = patch.object(browser_session, 'sync', side_effect=lambda: (
            True, st.session_state.get('_student_token'), True
        ))
        storage.start()
        self.addCleanup(storage.stop)
        st.cache_resource.clear()
        read_cache.clear()
        db.init_db()
        roster = Path(self.temp.name) / 'roster.csv'
        roster.write_text('Iniziali;Codice\nAA;1234\nBB;2345\nCC;3456\nDD;0123\n', encoding='utf-8')
        db.import_student_codes(roster)
        db.add_teacher('Docente test', 'Matematica')
        self.teacher_id = db.list_teachers()[0]['id']
        db.add_lesson(self.teacher_id, '2026-11-10', 1, 'Equazioni')
        self.lesson_id = db.list_lessons()[0]['id']
        for code in ['1234', '2345', '3456']:
            db.add_vote(self.lesson_id, code, 4)
        self.app = AppTest.from_file(str(Path(__file__).parents[1] / 'app.py'), default_timeout=30)

    def select_tab(self, label):
        self.app.session_state['active_tab'] = label
        self.app.run()
        self.assertEqual(len(self.app.exception), 0)

    def test_initial_page_skips_hidden_charts_and_reads_stats_once(self):
        with patch.object(db, 'teacher_stats', wraps=db.teacher_stats) as stats, patch.object(db, 'subject_history', wraps=db.subject_history) as history, patch.object(st, 'vega_lite_chart', wraps=st.vega_lite_chart) as charts:
            self.app.run()
            self.assertEqual(len(self.app.exception), 0)
            self.assertEqual(stats.call_count, 1)
            self.assertEqual(history.call_count, 0)
            self.assertEqual(charts.call_count, 0)
            self.assertEqual(len(self.app.dataframe), 0)
            self.select_tab('🏆 Classifica')
            self.assertEqual(stats.call_count, 1)
            self.assertEqual(history.call_count, 0)
            self.assertGreater(len(self.app.dataframe), 0)
            self.select_tab('📈 Grafici')
            self.assertEqual(stats.call_count, 1)
            self.assertEqual(history.call_count, 1)
            self.assertEqual(charts.call_count, 2)

    def test_voter_code_survives_tabs_and_vote_refreshes_results(self):
        self.app.run()
        self.app.text_input(key='login_code').input('0123')
        next(b for b in self.app.button if b.label == 'Accedi per votare').click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.select_tab('📈 Grafici')
        self.select_tab('🗳️ Vota')
        self.assertGreater(len(self.app.radio), 0)
        self.assertEqual(len(self.app.text_input), 0)
        self.app.radio[0].set_value(5)
        next(button for button in self.app.button if button.label == 'Invia il voto').click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 4)
        self.select_tab('🏆 Classifica')
        self.assertEqual(next(m.value for m in self.app.metric if m.label == 'Voti totali'), '4')

    def test_manual_refresh_reads_external_votes_and_keeps_selected_tab(self):
        self.app.run()
        self.select_tab('🏆 Classifica')
        self.assertEqual(next(m.value for m in self.app.metric if m.label == 'Voti totali'), '3')
        db.add_vote(self.lesson_id, '0123', 5)
        self.app.button(key='refresh_results').click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(self.app.session_state['active_tab'], '🏆 Classifica')
        self.assertEqual(next(m.value for m in self.app.metric if m.label == 'Voti totali'), '4')

    def test_logout_revokes_server_session(self):
        import voter_auth
        self.app.run()
        self.app.text_input(key='login_code').input('0123')
        next(b for b in self.app.button if b.label == 'Accedi per votare').click().run()
        token = self.app.session_state['_student_token']
        self.assertTrue(voter_auth.is_authenticated(token))
        self.app.button(key='student_logout').click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertFalse(voter_auth.is_authenticated(token))
        self.assertEqual(len(self.app.radio), 0)
        self.assertEqual(len(self.app.text_input), 1)

    def test_admin_still_adds_teacher_on_demand(self):
        self.app.run()
        self.select_tab('⚙️ Gestione')
        next(field for field in self.app.text_input if field.label == 'PIN amministratore').input('test-only-pin')
        next(button for button in self.app.button if button.label == 'Accedi').click().run()
        self.assertEqual(len(self.app.exception), 0)
        next(field for field in self.app.text_input if field.label == 'Nome da mostrare').input('Nuovo docente')
        next(field for field in self.app.text_input if field.label == 'Materia').input('Storia')
        next(button for button in self.app.button if button.label == 'Aggiungi professore').click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(len(db.list_teachers()), 2)

    def test_logout_from_admin_then_return_to_vote(self):
        self.app.run()
        self.app.text_input(key='login_code').input('0123')
        next(b for b in self.app.button if b.label == 'Accedi per votare').click().run()
        self.select_tab('⚙️ Gestione')
        self.app.button(key='student_logout').click().run()
        self.select_tab('🗳️ Vota')
        self.assertEqual(len(self.app.text_input), 1)
        self.assertEqual(self.app.text_input[0].key, 'login_code')
