import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import database as db
import voter_auth as auth


class SessionCases:
    def test_session_is_hashed_and_expires_at_exact_deadline(self):
        token, expiry, retry = auth.login('0123', now=100)
        self.assertEqual(retry, 0)
        self.assertEqual(expiry, 100 + auth.SESSION_SECONDS)
        with db.connect() as con:
            row = con.execute('SELECT token_hash, voter_digest, expires_at FROM student_sessions').fetchone()
        self.assertEqual(row['token_hash'], hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token, str(tuple(row)))
        self.assertNotIn('0123', str(tuple(row)))
        self.assertTrue(auth.is_authenticated(token, now=expiry - 1))
        self.assertFalse(auth.is_authenticated(token, now=expiry))
        self.assertFalse(auth.is_authenticated(token + 'x', now=101))
        self.assertFalse(auth.is_authenticated('x' * 43, now=101))

    def test_logout_revokes_only_current_device_and_survives_reloads(self):
        first, _, _ = auth.login('0123')
        second, _, _ = auth.login('0123')
        self.assertNotEqual(first, second)
        db.init_db()
        self.assertTrue(auth.is_authenticated(first))
        auth.logout(first)
        self.assertFalse(auth.is_authenticated(first))
        self.assertTrue(auth.is_authenticated(second))
        auth.logout(first)  # Idempotent.
        with self.assertRaises(ValueError):
            auth.add_vote(self.lessons[0]['id'], first, 4)

    def test_session_vote_uses_existing_participation_and_anonymous_vote(self):
        db.add_vote(self.lessons[0]['id'], '0123', 4)
        token, _, _ = auth.login('0123')
        self.assertEqual([r['id'] for r in auth.list_lessons(token)], [self.lessons[1]['id']])
        with self.assertRaises(db.INTEGRITY_ERRORS):
            auth.add_vote(self.lessons[0]['id'], token, 5)
        auth.add_vote(self.lessons[1]['id'], token, 5)
        self.assertEqual(auth.list_lessons(token), [])
        with db.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM participation').fetchone()[0], 2)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM votes').fetchone()[0], 2)
        self.assertEqual(db.teacher_stats()[0]['average_rating'], 4.5)

    def test_expired_token_cannot_read_lessons_or_submit_vote(self):
        token, _, _ = auth.login('0123', now=1)
        with self.assertRaises(ValueError):
            auth.list_lessons(token)
        with self.assertRaises(ValueError):
            auth.add_vote(self.lessons[0]['id'], token, 5)
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 0)

    def test_failed_logins_are_committed_global_and_not_reset_by_valid_code(self):
        for _ in range(auth.MAX_FAILURES - 1):
            self.assertIsNone(auth.login('9999', now=100)[0])
        self.assertIsNotNone(auth.login('0123', now=101)[0])
        token, _, retry = auth.login('bad', now=102)
        self.assertIsNone(token)
        self.assertGreater(retry, 0)
        db.init_db()  # New page/process cannot clear the database limit.
        self.assertIsNone(auth.login('0123', now=103)[0])
        self.assertIsNotNone(auth.login('0123', now=100 + auth.LOGIN_WINDOW)[0])

    def test_failed_vote_keeps_session_and_rolls_back_participation(self):
        token, _, _ = auth.login('0123')
        with self.assertRaises(ValueError):
            auth.add_vote(self.lessons[0]['id'], token, 9)
        self.assertTrue(auth.is_authenticated(token))
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 0)
        auth.add_vote(self.lessons[0]['id'], token, 3)
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 1)


class SQLiteSessionTests(SessionCases, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        backend = patch.object(db.postgres, 'enabled', return_value=False)
        backend.start()
        self.addCleanup(backend.stop)
        path = patch.object(db, 'DB_PATH', Path(self.temp.name) / 'votes.sqlite3')
        path.start()
        self.addCleanup(path.stop)
        db.init_db()
        roster = Path(self.temp.name) / 'codes.csv'
        roster.write_text('Iniziali;Codice\nAA;1234\nBB;2345\nCC;3456\nDD;0123\n', encoding='utf-8')
        db.import_student_codes(roster)
        db.add_teacher('Docente', 'Materia')
        teacher_id = db.list_teachers()[0]['id']
        db.add_lesson(teacher_id, '2026-11-10', 1, 'Prima')
        db.add_lesson(teacher_id, '2026-11-10', 5, 'Seconda')
        self.lessons = db.lessons_on('2026-11-10')
