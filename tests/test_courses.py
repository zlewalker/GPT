"""Atomic course completion: preserve previous votes and reuse lesson statistics."""
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

import courses
import database as db
import migrate
import voter_auth
import test_database


class CourseTests(unittest.TestCase):
    setUp = test_database.DatabaseTests.setUp
    tearDown = test_database.DatabaseTests.tearDown

    def token(self, code='1234'):
        return voter_auth.login(code)[0]

    def test_closure_blocks_new_lessons_but_old_votes_still_work(self):
        courses.set_closed(self.teacher_id, True)
        with self.assertRaises(ValueError):
            db.add_lesson(self.teacher_id, '2026-11-11', 1)
        db.add_vote(self.lessons[0]['id'], '1234', 5)
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 1)
        courses.set_closed(self.teacher_id, False)
        db.add_lesson(self.teacher_id, '2026-11-11', 1)
        self.assertFalse(db.list_teachers()[0]['is_closed'])

    def test_completion_requires_closed_course(self):
        with self.assertRaises(ValueError):
            voter_auth.complete_course(self.teacher_id, self.token(), 5, 2)
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 0)

    def test_fills_only_missing_votes_preserving_old_rows(self):
        db.add_vote(self.lessons[0]['id'], '1234', 2)
        with db.connect() as con:
            before = [tuple(row) for row in con.execute('SELECT * FROM votes')]
        courses.set_closed(self.teacher_id, True)
        token = self.token()
        pending = voter_auth.list_courses(token)[0]
        self.assertEqual(pending['missing_lessons'], 1)
        self.assertEqual(pending['voted_lessons'], 1)
        self.assertEqual(voter_auth.complete_course(self.teacher_id, token, 5, 1), 1)
        with db.connect() as con:
            after = [tuple(row) for row in con.execute('SELECT * FROM votes')]
        self.assertTrue(set(before).issubset(after))
        self.assertEqual(db.teacher_stats()[0]['average_rating'], 3.5)
        self.assertEqual(voter_auth.list_courses(token), [])
        self.assertEqual(voter_auth.list_courses(token, True)[0]['missing_lessons'], 0)
        with self.assertRaises(ValueError):
            voter_auth.complete_course(self.teacher_id, token, 1, 0)

    def test_completion_without_any_previous_votes(self):
        courses.set_closed(self.teacher_id, True)
        token = self.token()
        self.assertEqual(voter_auth.complete_course(self.teacher_id, token, 4, 2), 2)
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 2)
        self.assertEqual(db.teacher_stats()[0]['average_rating'], 4)
        self.assertEqual(voter_auth.list_lessons(token), [])
        with self.assertRaises(db.INTEGRITY_ERRORS):
            voter_auth.add_vote(self.lessons[0]['id'], token, 5)

    def test_reopen_preserves_votes_and_allows_new_lesson_recovery(self):
        courses.set_closed(self.teacher_id, True)
        token = self.token()
        voter_auth.complete_course(self.teacher_id, token, 4, 2)
        courses.set_closed(self.teacher_id, False)
        self.assertEqual(voter_auth.list_courses(token, True), [])
        db.add_lesson(self.teacher_id, '2026-11-11', 1)
        courses.set_closed(self.teacher_id, True)
        self.assertEqual(voter_auth.complete_course(self.teacher_id, token, 5, 1), 1)
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 3)

    def test_revoked_session_cannot_list_or_complete_courses(self):
        courses.set_closed(self.teacher_id, True)
        token = self.token()
        voter_auth.logout(token)
        with self.assertRaises(ValueError):
            voter_auth.list_courses(token)
        with self.assertRaises(ValueError):
            voter_auth.complete_course(self.teacher_id, token, 5, 2)

    def test_failure_rolls_back_the_entire_batch(self):
        courses.set_closed(self.teacher_id, True)
        token = self.token()
        with patch.object(courses.secrets, 'token_hex', return_value='duplicate-test-id'):
            with self.assertRaises(db.INTEGRITY_ERRORS):
                voter_auth.complete_course(self.teacher_id, token, 5, 2)
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 0)
        with db.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM participation').fetchone()[0], 0)
        self.assertEqual(voter_auth.complete_course(self.teacher_id, token, 5, 2), 2)

    def test_completed_ratings_have_no_student_session_timestamp_or_batch_id(self):
        courses.set_closed(self.teacher_id, True)
        voter_auth.complete_course(self.teacher_id, self.token(), 5, 2)
        with db.connect() as con:
            rows = con.execute('SELECT * FROM votes').fetchall()
            self.assertEqual(set(rows[0].keys()), {'id', 'lesson_id', 'rating'})
            self.assertEqual(len({row['id'] for row in rows}), 2)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM participation').fetchone()[0], 2)

    def test_concurrent_recovery_does_not_duplicate_any_lesson(self):
        courses.set_closed(self.teacher_id, True)
        token = self.token()
        def submit(_):
            try:
                voter_auth.complete_course(self.teacher_id, token, 4, 2)
                return True
            except (ValueError,) + db.INTEGRITY_ERRORS:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(submit, range(4))), 1)
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 2)

    def test_course_backup_preserves_completion_and_status(self):
        courses.set_closed(self.teacher_id, True)
        voter_auth.complete_course(self.teacher_id, self.token(), 4, 2)
        with db.connect() as con:
            data = migrate.read_rows(con)
        migrate.validate(data)
        self.assertEqual(len(data['votes']), 2)
        self.assertEqual(data['course_state'], [[self.teacher_id, 1]])
        data['course_state'][0][1] = 9
        with self.assertRaises(ValueError):
            migrate.validate(data)

    def test_stale_preview_does_not_silently_vote_a_different_count(self):
        courses.set_closed(self.teacher_id, True)
        token = self.token()
        self.assertEqual(voter_auth.list_courses(token)[0]['missing_lessons'], 2)
        voter_auth.add_vote(self.lessons[0]['id'], token, 3)
        with self.assertRaises(ValueError):
            voter_auth.complete_course(self.teacher_id, token, 5, 2)
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 1)

    def test_completion_updates_all_lesson_aggregates(self):
        courses.set_closed(self.teacher_id, True)
        for code in ('1234', '2345', '3456'):
            voter_auth.complete_course(self.teacher_id, self.token(code), 5, 2)
        stats = db.teacher_stats()[0]
        self.assertEqual(stats['total_votes'], 6)
        self.assertEqual(stats['average_rating'], 5)
        self.assertEqual(stats['rating_5'], 6)
        self.assertEqual(len(db.teacher_history(self.teacher_id)), 2)

    def test_does_not_fill_another_teacher_or_subject(self):
        db.add_teacher('Altro docente', 'Altra materia')
        other = next(row for row in db.list_teachers() if row['id'] != self.teacher_id)
        db.add_lesson(other['id'], '2026-11-10', 1)
        courses.set_closed(self.teacher_id, True)
        token = self.token()
        voter_auth.complete_course(self.teacher_id, token, 5, 2)
        self.assertEqual(len(voter_auth.list_lessons(token)), 1)
        self.assertEqual(voter_auth.list_lessons(token)[0]['teacher_id'], other['id'])

    def test_bulk_recovery_has_bounded_database_round_trips(self):
        from contextlib import contextmanager
        for day in range(1, 29):
            db.add_lesson(self.teacher_id, f'2026-10-{day:02d}', 1)
        courses.set_closed(self.teacher_id, True)
        token = self.token()
        original_connect = db.connect
        queries = []

        class TrackedConnection:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, sql, parameters=()):
                queries.append(sql)
                return self.connection.execute(sql, parameters)

        @contextmanager
        def tracked_connect():
            with original_connect() as connection:
                yield TrackedConnection(connection)

        with patch.object(db, 'connect', tracked_connect):
            self.assertEqual(voter_auth.complete_course(self.teacher_id, token, 5, 30), 30)
        self.assertLessEqual(len(queries), 6)
        self.assertEqual(sum(sql.startswith('INSERT') for sql in queries), 2)
