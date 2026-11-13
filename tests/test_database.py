import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database as db


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.backend = patch.object(db.postgres, 'enabled', return_value=False)
        self.backend.start()
        self.addCleanup(self.backend.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.previous = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / 'db.sqlite3'
        db.init_db()
        self.roster = Path(self.temp.name) / 'codes.csv'
        self.roster.write_text('Iniziali;Codice\nAA;1234\nBB;2345\nCC;3456\nDD;0123\n', encoding='utf-8')
        db.import_student_codes(self.roster)
        db.add_teacher('Prof. Prova', 'Matematica')
        self.teacher_id = db.list_teachers()[0]['id']
        db.add_lesson(self.teacher_id, '2026-11-10', 1, 'Equazioni')
        db.add_lesson(self.teacher_id, '2026-11-10', 2, 'Grafici')
        self.lessons = db.lessons_on('2026-11-10')

    def tearDown(self):
        db.DB_PATH = self.previous
        self.temp.cleanup()

    def test_same_code_cannot_vote_twice_on_same_lesson(self):
        db.add_vote(self.lessons[0]['id'], '1234', 5, '2026-11-10')
        with self.assertRaises(sqlite3.IntegrityError):
            db.add_vote(self.lessons[0]['id'], '1234', 2, '2026-11-10')
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 1)

    def test_same_code_can_vote_on_another_lesson(self):
        for lesson in self.lessons:
            db.add_vote(lesson['id'], '1234', 5, '2026-11-10')
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 2)

    def test_average_and_history(self):
        for code, rating in [('1234', 4), ('2345', 5), ('3456', 3)]:
            db.add_vote(self.lessons[0]['id'], code, rating, '2026-11-10')
        stats = db.teacher_stats()[0]
        self.assertEqual(stats['average_rating'], 4)
        self.assertEqual(stats['total_votes'], 3)
        history = db.teacher_history(self.teacher_id, 3)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['average_rating'], 4)

    def test_teacher_vote_distribution_includes_all_lessons(self):
        for code, rating in [('1234', 1), ('2345', 5), ('3456', 5)]:
            db.add_vote(self.lessons[0]['id'], code, rating)
        db.add_vote(self.lessons[1]['id'], '1234', 3)
        db.add_teacher('Senza voti', 'Storia')
        stats = {r['name']: r for r in db.teacher_stats()}
        self.assertEqual([stats['Prof. Prova'][f'rating_{i}'] for i in range(1, 6)], [1, 0, 1, 0, 2])
        self.assertEqual(sum(stats['Prof. Prova'][f'rating_{i}'] for i in range(1, 6)), stats['Prof. Prova']['total_votes'])
        self.assertEqual([stats['Senza voti'][f'rating_{i}'] for i in range(1, 6)], [0] * 5)

    def test_votes_have_no_deadline(self):
        db.add_vote(self.lessons[0]['id'], '1234', 3, '2027-06-30')
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 1)
        with self.assertRaises(sqlite3.IntegrityError):
            db.add_vote(self.lessons[0]['id'], '1234', 5, '2028-01-01')

    def test_ratings_have_no_student_identifier_or_timestamp(self):
        db.add_vote(self.lessons[0]['id'], '1234', 4, '2026-11-10')
        with db.connect() as con:
            columns = {row['name'] for row in con.execute('PRAGMA table_info(votes)')}
            self.assertEqual(columns, {'id', 'lesson_id', 'rating'})
            self.assertEqual(con.execute('SELECT COUNT(*) FROM participation').fetchone()[0], 1)
            digest = con.execute('SELECT voter_digest FROM students LIMIT 1').fetchone()[0]
            self.assertEqual(len(digest), 64)

    def test_subject_history_matches_per_teacher_results_in_one_connection(self):
        for code, rating in [('1234', 4), ('2345', 5), ('3456', 3)]:
            db.add_vote(self.lessons[0]['id'], code, rating)
        db.add_vote(self.lessons[1]['id'], '1234', 2)  # Below visibility threshold.
        db.add_teacher('Secondo docente', 'Matematica')
        second = next(t for t in db.list_teachers() if t['name'] == 'Secondo docente')
        db.add_lesson(second['id'], '2026-11-11', 5, 'Geometria')
        second_lesson = db.list_lessons()[0]['id']
        for code in ['1234', '2345', '3456']:
            db.add_vote(second_lesson, code, 5)
        db.add_teacher('Altra materia', 'Storia')
        other = next(t for t in db.list_teachers() if t['name'] == 'Altra materia')
        db.add_lesson(other['id'], '2026-11-12', 1, 'Storia')
        for code in ['1234', '2345', '3456']:
            db.add_vote(db.list_lessons()[0]['id'], code, 1)
        expected = [
            dict(row, teacher_name=teacher['name'])
            for teacher in db.list_teachers() if teacher['subject'] == 'Matematica'
            for row in db.teacher_history(teacher['id'])
        ]
        expected.sort(key=lambda r: (r['lesson_date'], r['slot'], r['teacher_name']))
        with patch.object(db, 'connect', wraps=db.connect) as connect:
            actual = db.subject_history('Matematica')
        self.assertEqual(connect.call_count, 1)
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 2)
        self.assertEqual(db.subject_history('Materia inesistente'), [])

    def test_admin_locks_after_five_failures_and_expires(self):
        for attempt in range(1, 6):
            ok, remaining, lock = db.admin_login('wrong', 'correct', now=100)
            self.assertFalse(ok)
            self.assertEqual(remaining, 5 - attempt)
            self.assertEqual(lock, 900 if attempt == 5 else 0)
        db.init_db()  # A reload/reinitialization must not clear the lock.
        self.assertFalse(db.admin_login('correct', 'correct', now=101)[0])
        self.assertTrue(db.admin_login('correct', 'correct', now=1000)[0])

    def test_admin_success_resets_failures(self):
        db.admin_login('wrong', 'correct', now=100)
        self.assertTrue(db.admin_login('correct', 'correct', now=101)[0])
        self.assertEqual(db.admin_login('wrong', 'correct', now=102)[1], 4)

    def test_long_lesson_has_one_vote_and_no_extra_weight(self):
        db.add_lesson(self.teacher_id, '2026-11-10', 3, duration_hours=4)
        long_lesson = db.lessons_on('2026-11-10')[-1]
        self.assertEqual(long_lesson['duration_hours'], 4)
        db.add_vote(long_lesson['id'], '1234', 5, '2026-11-10')
        with self.assertRaises(sqlite3.IntegrityError):
            db.add_vote(long_lesson['id'], '1234', 1, '2026-11-10')
        db.add_vote(self.lessons[0]['id'], '1234', 1, '2026-11-10')
        self.assertEqual(db.teacher_stats()[0]['average_rating'], 3)

    def test_year_and_migration_preserve_votes(self):
        db.add_vote(self.lessons[0]['id'], '1234', 5, '2026-11-10')
        db.init_db()
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 1)
        with db.connect() as con:
            self.assertEqual(con.execute("SELECT value FROM settings WHERE key='school_year'").fetchone()[0], '2026/2027')

    def test_history_requires_three_votes(self):
        for number in range(2):
            db.add_vote(self.lessons[0]['id'], ['1234', '2345'][number], 5, '2026-11-10')
        self.assertEqual(db.teacher_history(self.teacher_id), [])
        db.add_vote(self.lessons[0]['id'], '3456', 5, '2026-11-10')
        self.assertEqual(len(db.teacher_history(self.teacher_id)), 1)

    def test_rounding_at_tier_boundaries(self):
        from rules import rounded_score, tier_for
        for score, expected in [(4.495, 'S'), (4.4949, 'A'), (3.995, 'A'), (2.995, 'B'), (1.995, 'C'), (1.9949, 'D')]:
            with self.subTest(score=score):
                self.assertEqual(tier_for(score), expected)
        self.assertEqual(rounded_score(4.495), 4.5)
        import migrate, json
        payload = json.loads(migrate.export_backup_bytes().decode('utf-8'))
        self.assertEqual(payload['format'], 1)
        migrate.validate(payload['data'])

    def test_ranking_orders_by_rounded_score_then_total_votes(self):
        # Two teachers with the same displayed rounded average (4.33) are ordered by total_votes DESC.
        db.add_teacher('Docente Molti Voti', 'Fisica')
        many_id = next(t['id'] for t in db.list_teachers() if t['name'] == 'Docente Molti Voti')
        db.add_lesson(many_id, '2026-11-11', 1, 'L1')
        db.add_lesson(many_id, '2026-11-11', 5, 'L2')
        many_lessons = db.lessons_on('2026-11-11')
        for code, rating in [('1234', 5), ('2345', 4), ('3456', 4)]:
            db.add_vote(many_lessons[0]['id'], code, rating)
            db.add_vote(many_lessons[1]['id'], code, rating)
        for code, rating in [('1234', 5), ('2345', 4), ('3456', 4)]:
            db.add_vote(self.lessons[0]['id'], code, rating)
        ranked = [r['name'] for r in db.teacher_stats() if r['total_votes'] > 0]
        self.assertEqual(ranked, ['Docente Molti Voti', 'Prof. Prova'])
        # Even if raw averages differ slightly (4.496 vs 4.504), equal rounded scores (4.50) sort by total_votes DESC, then raw average DESC.
        sample = [
            {'id': 1, 'name': 'Pochi Voti', 'subject': 'M1', 'total_votes': 3, 'rated_lessons': 1,
             'rating_1': 0, 'rating_2': 0, 'rating_3': 0, 'rating_4': 1, 'rating_5': 2, 'average_rating': 4.504},
            {'id': 2, 'name': 'Tanti Voti Minore', 'subject': 'M2', 'total_votes': 10, 'rated_lessons': 3,
             'rating_1': 0, 'rating_2': 0, 'rating_3': 0, 'rating_4': 5, 'rating_5': 5, 'average_rating': 4.496},
            {'id': 3, 'name': 'Tanti Voti Maggiore', 'subject': 'M3', 'total_votes': 10, 'rated_lessons': 3,
             'rating_1': 0, 'rating_2': 0, 'rating_3': 0, 'rating_4': 5, 'rating_5': 5, 'average_rating': 4.504},
        ]
        with patch.object(db, '_dicts', side_effect=lambda cur: (cur.fetchall(), list(sample))[1]):
            ordered = db.teacher_stats()
        self.assertEqual([r['name'] for r in ordered], ['Tanti Voti Maggiore', 'Tanti Voti Minore', 'Pochi Voti'])


    def test_unknown_codes_are_rejected(self):
        for code in ['9999', 'inventato', '123', '12345']:
            with self.assertRaises(ValueError):
                db.add_vote(self.lessons[0]['id'], code, 5, '2026-11-10')
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 0)

    def test_leading_zero_and_idempotent_import(self):
        db.import_student_codes(self.roster)
        self.assertEqual(db.student_count(), 4)
        db.add_vote(self.lessons[0]['id'], '0123', 5, '2026-11-10')
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 1)

    def test_vote_failure_rolls_back_participation(self):
        with db.connect() as con:
            con.execute("CREATE TRIGGER reject_vote BEFORE INSERT ON votes BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            db.add_vote(self.lessons[0]['id'], '1234', 5, '2026-11-10')
        with db.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM participation').fetchone()[0], 0)
            con.execute('DROP TRIGGER reject_vote')
        db.add_vote(self.lessons[0]['id'], '1234', 5, '2026-11-10')

    def test_concurrent_submissions_record_only_one_vote(self):
        from concurrent.futures import ThreadPoolExecutor
        def submit(_):
            try:
                db.add_vote(self.lessons[0]['id'], '1234', 5, '2026-11-10')
                return True
            except sqlite3.IntegrityError:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(submit, range(4))), 1)
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 1)

    def test_legacy_migration_preserves_results_and_duplicate_block(self):
        with db.connect() as con:
            con.execute('DROP TABLE votes')
            con.execute('CREATE TABLE votes (id INTEGER PRIMARY KEY, lesson_id INTEGER, voter_digest TEXT, rating INTEGER, created_at TEXT)')
            digest = db.code_digest(con, '1234')
            con.execute('INSERT INTO votes VALUES (1, ?, ?, 5, CURRENT_TIMESTAMP)', (self.lessons[0]['id'], digest))
        db.init_db()
        self.assertTrue(db.DB_PATH.with_name(db.DB_PATH.name + '.before_anonymous.bak').exists())
        self.assertEqual(db.teacher_stats()[0]['average_rating'], 5)
        with self.assertRaises(sqlite3.IntegrityError):
            db.add_vote(self.lessons[0]['id'], '1234', 1, '2026-11-10')
        db.init_db()
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 1)


    def test_lesson_order_is_insertion_order(self):
        db.add_lesson(self.teacher_id, '2026-09-01', 5, 'Aggiunta per ultima')
        rows = db.list_lessons('1234')
        self.assertEqual(rows[0]['topic'], 'Aggiunta per ultima')
        self.assertEqual([r['id'] for r in rows], sorted([r['id'] for r in rows], reverse=True))

    def test_personal_pending_filter_and_all_view(self):
        db.add_vote(self.lessons[0]['id'], '1234', 4)
        pending = db.list_lessons('1234')
        self.assertEqual([r['id'] for r in pending], [self.lessons[1]['id']])
        all_rows = db.list_lessons('1234', include_voted=True)
        self.assertEqual(len(all_rows), 2)
        self.assertTrue(next(r for r in all_rows if r['id'] == self.lessons[0]['id'])['has_voted'])
        self.assertEqual(len(db.list_lessons('2345')), 2)
        with self.assertRaises(ValueError):
            db.list_lessons('9999')

    def test_rename_preserves_votes_participation_and_order(self):
        db.add_vote(self.lessons[0]['id'], '1234', 5)
        with db.connect() as con:
            before_votes = [tuple(row) for row in con.execute('SELECT * FROM votes')]
            before_participation = [tuple(row) for row in con.execute('SELECT * FROM participation')]
        order = [row['id'] for row in db.list_lessons()]
        db.update_lesson_title(self.lessons[0]['id'], 'Titolo corretto')
        with db.connect() as con:
            self.assertEqual(before_votes, [tuple(row) for row in con.execute('SELECT * FROM votes')])
            self.assertEqual(before_participation, [tuple(row) for row in con.execute('SELECT * FROM participation')])
        self.assertEqual(order, [row['id'] for row in db.list_lessons()])
        self.assertEqual(db.lessons_on('2026-11-10')[0]['topic'], 'Titolo corretto')
        for invalid in ['', 'x' * 151]:
            with self.assertRaises(ValueError):
                db.update_lesson_title(self.lessons[0]['id'], invalid)

    def test_duration_fixed_at_four_and_period_labels(self):
        for duration in [1, 3, 5]:
            with self.assertRaises(ValueError):
                db.add_lesson(self.teacher_id, '2026-11-11', 1, duration_hours=duration)
        self.assertEqual(db.period_label(1), 'Mattina')
        self.assertEqual(db.period_label(5), 'Pomeriggio')
        db.add_lesson(self.teacher_id, '2026-11-11', 5)
        self.assertEqual(db.lessons_on('2026-11-11')[0]['duration_hours'], 4)


    def test_change_period_preserves_votes_and_participation(self):
        db.add_vote(self.lessons[0]['id'], '1234', 5)
        db.update_lesson(self.lessons[0]['id'], 'Correzione', 'Pomeriggio')
        row = next(r for r in db.list_lessons() if r['id'] == self.lessons[0]['id'])
        self.assertEqual(row['slot'], 5)
        self.assertEqual(row['topic'], 'Correzione')
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 1)
        with self.assertRaises(sqlite3.IntegrityError):
            db.add_vote(row['id'], '1234', 3)
        with self.assertRaises(ValueError):  # Another legacy lesson still occupies the morning.
            db.update_lesson(row['id'], 'Ancora corretta', 'Mattina')
        self.assertEqual(db.teacher_stats()[0]['average_rating'], 5)

    def test_period_conflict_does_not_change_title_or_votes(self):
        db.add_lesson(self.teacher_id, '2026-11-10', 5, 'Pomeriggio')
        db.add_vote(self.lessons[0]['id'], '1234', 4)
        with self.assertRaises(ValueError):
            db.update_lesson(self.lessons[0]['id'], 'Non salvare', 'Pomeriggio')
        row = next(r for r in db.list_lessons() if r['id'] == self.lessons[0]['id'])
        self.assertEqual(row['topic'], 'Equazioni')
        self.assertEqual(row['slot'], 1)
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 1)


if __name__ == '__main__':
    unittest.main()
