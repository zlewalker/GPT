"""Real driver tests, isolated in a disposable schema; opt in with TEST_DATABASE_URL."""
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import database as db
import migrate
import postgres
import test_database as original


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'TEST_DATABASE_URL not configured')
class PostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.schema = 'votes_test_' + secrets.token_hex(8)
        cls.role = cls.schema + '_runtime'
        cls.env = patch.dict(os.environ, {
            'DATABASE_URL': os.environ['TEST_DATABASE_URL'],
            'DATABASE_SCHEMA': cls.schema,
        })
        cls.env.start()
        with postgres.connect() as con:
            # Supabase has these roles; a dedicated local CI database does not.
            for role in ('anon', 'authenticated'):
                con.raw.execute(f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{role}') THEN CREATE ROLE {role} NOLOGIN; END IF; END $$")
            schema = (Path(__file__).parents[1] / 'sql/schema.sql').read_text(encoding='utf-8')
            con.raw.execute(schema.replace('votes_app', cls.schema).replace('votes_runtime', cls.role))

    @classmethod
    def tearDownClass(cls):
        try:
            with postgres.connect() as con:
                con.raw.execute(f'DROP SCHEMA "{cls.schema}" CASCADE')
                con.raw.execute(f'DROP ROLE "{cls.role}"')
        finally:
            cls.env.stop()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.roster = Path(self.temp.name) / 'codes.csv'
        self.roster.write_text('Iniziali;Codice\nAA;1234\nBB;2345\nCC;3456\nDD;0123\n', encoding='utf-8')
        with postgres.connect() as con:
            con.execute('TRUNCATE participation, votes, lessons, teachers, students, settings RESTART IDENTITY CASCADE')
            for key, value in [('schema_version', '1'), ('migration_ready', '1'), ('school_year', db.SCHOOL_YEAR), ('voter_key', secrets.token_hex(32))]:
                con.execute('INSERT INTO settings VALUES (?, ?)', (key, value))
        db.init_db()
        db.import_student_codes(self.roster)
        db.add_teacher('Prof. Prova', 'Matematica')
        self.teacher_id = db.list_teachers()[0]['id']
        db.add_lesson(self.teacher_id, '2026-11-10', 1, 'Equazioni')
        db.add_lesson(self.teacher_id, '2026-11-10', 2, 'Grafici')
        self.lessons = db.lessons_on('2026-11-10')

    def tearDown(self):
        self.temp.cleanup()

    def assertRaises(self, expected, *args, **kwargs):
        # Original SQLite business tests expect the equivalent driver error.
        if expected is sqlite3.IntegrityError:
            expected = db.INTEGRITY_ERRORS
        return super().assertRaises(expected, *args, **kwargs)

    def test_vote_failure_rolls_back_participation(self):
        with postgres.connect() as con:
            con.execute('ALTER TABLE votes ADD CONSTRAINT reject_test_vote CHECK (rating < 0)')
        with self.assertRaises(db.INTEGRITY_ERRORS):
            db.add_vote(self.lessons[0]['id'], '1234', 5)
        with postgres.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM participation').fetchone()[0], 0)
            con.execute('ALTER TABLE votes DROP CONSTRAINT reject_test_vote')

    def test_unmigrated_database_fails_closed(self):
        with postgres.connect() as con:
            con.execute("DELETE FROM settings WHERE key = 'migration_ready'")
        with self.assertRaises(RuntimeError):
            db.init_db()

    def test_streamlit_with_postgres_ranking_and_history(self):
        from streamlit.testing.v1 import AppTest
        for code in ['1234', '2345', '3456']:
            db.add_vote(self.lessons[0]['id'], code, 4)
        app = AppTest.from_file(str(Path(__file__).parents[1] / 'app.py'), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.tabs), 4)
        self.assertGreater(len(app.dataframe), 0)
        app.text_input(key='voter_code').input('0123').run()
        self.assertEqual(len(app.exception), 0)

    def test_runtime_role_can_vote_but_cannot_change_roster_or_delete(self):
        import psycopg
        with postgres.connect() as con:
            digest = db.code_digest(con, '1234')
            con.execute(f'SET LOCAL ROLE "{self.role}"')
            con.execute('INSERT INTO participation VALUES (?, ?)', (self.lessons[0]['id'], digest))
            con.execute('INSERT INTO votes VALUES (?, ?, ?)', ('runtime-test-vote', self.lessons[0]['id'], 4))
            con.execute('UPDATE lessons SET topic = ?, slot = ? WHERE id = ?', ('Corrected', 5, self.lessons[0]['id']))
            self.assertEqual(con.execute('SELECT COUNT(*) FROM students').fetchone()[0], 4)
            for forbidden in [
                "INSERT INTO students VALUES ('bad', 'bad')",
                'DELETE FROM votes',
                'ALTER TABLE votes ADD COLUMN forbidden INTEGER',
            ]:
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with con.raw.transaction():
                        con.execute(forbidden)
        self.assertEqual(db.teacher_stats()[0]['total_votes'], 1)

    def test_migration_exact_comparison_and_repeat_refusal(self):
        db.add_vote(self.lessons[0]['id'], '0123', 5)
        with postgres.connect() as con:
            source = migrate.read_rows(con)
            con.execute('TRUNCATE participation, votes, lessons, teachers, students, settings RESTART IDENTITY CASCADE')
            con.execute("INSERT INTO settings VALUES ('schema_version', '1')")
        migrate.import_postgres(source)
        with postgres.connect() as con:
            migrate.verify(con, source)
        self.assertEqual(len(db.list_lessons('0123')), 1)
        with self.assertRaises(ValueError):
            migrate.import_postgres(source)
        db.add_teacher('Second', 'Second')
        self.assertGreater(max(t['id'] for t in db.list_teachers()), self.teacher_id)

    def test_migration_failure_rolls_back_every_table(self):
        with postgres.connect() as con:
            source = migrate.read_rows(con)
            con.execute('TRUNCATE participation, votes, lessons, teachers, students, settings RESTART IDENTITY CASCADE')
            con.execute("INSERT INTO settings VALUES ('schema_version', '1')")
        with patch.object(migrate, 'verify', side_effect=ValueError('forced failure')):
            with self.assertRaises(ValueError):
                migrate.import_postgres(source)
        with postgres.connect() as con:
            self.assertFalse(any(migrate.read_rows(con).values()))

    def test_sqlite_transfer_export_and_restore_round_trip(self):
        from contextlib import redirect_stdout
        from io import StringIO
        source_path = Path(self.temp.name) / 'source.sqlite3'
        with patch.object(db, 'DB_PATH', source_path), patch.object(postgres, 'enabled', return_value=False):
            db.init_db()
            db.import_student_codes(self.roster)
            db.add_teacher('Source teacher', 'Source subject')
            db.add_lesson(db.list_teachers()[0]['id'], '2026-11-10', 1, 'Source lesson')
            db.add_vote(db.list_lessons()[0]['id'], '0123', 5)
        with postgres.connect() as con:
            con.execute('TRUNCATE participation, votes, lessons, teachers, students, settings RESTART IDENTITY CASCADE')
            con.execute("INSERT INTO settings VALUES ('schema_version', '1')")
        with redirect_stdout(StringIO()):
            self.assertEqual(migrate.main(['--source', str(source_path), '--apply', '--backup-dir', self.temp.name]), 0)
            self.assertEqual(migrate.main(['--source', str(source_path), '--verify']), 0)
            export_dir = Path(self.temp.name) / 'export'
            self.assertEqual(migrate.main(['--export', '--backup-dir', str(export_dir)]), 0)
            backup = next(export_dir.glob('*.json'))
            with postgres.connect() as con:
                con.execute('TRUNCATE participation, votes, lessons, teachers, students, settings RESTART IDENTITY CASCADE')
                con.execute("INSERT INTO settings VALUES ('schema_version', '1')")
            self.assertEqual(migrate.main(['--restore', str(backup), '--backup-dir', self.temp.name]), 0)
            self.assertEqual(migrate.main(['--source', str(source_path), '--verify']), 0)
        self.assertEqual(db.list_lessons('0123'), [])
        self.assertEqual(db.teacher_stats()[0]['average_rating'], 5)


# Exercise the same business cases on both backends; SQL-specific tests stay separate.
for name in dir(original.DatabaseTests):
    if name.startswith('test_') and name not in {
        'test_legacy_migration_preserves_results_and_duplicate_block',
        'test_ratings_have_no_student_identifier_or_timestamp',
        'test_vote_failure_rolls_back_participation',
        'test_concurrent_submissions_record_only_one_vote',
    }:
        setattr(PostgresTests, name, getattr(original.DatabaseTests, name))


def concurrent_test(self):
    from concurrent.futures import ThreadPoolExecutor
    def submit(_):
        try:
            db.add_vote(self.lessons[0]['id'], '1234', 5)
            return True
        except db.INTEGRITY_ERRORS:
            return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        self.assertEqual(sum(pool.map(submit, range(4))), 1)
    with postgres.connect() as con:
        self.assertEqual(con.execute('SELECT COUNT(*) FROM participation').fetchone()[0], 1)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM votes').fetchone()[0], 1)


PostgresTests.test_concurrent_submissions_record_only_one_vote = concurrent_test
