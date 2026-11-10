import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database as db
import migrate
import postgres


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'source.sqlite3'
        self.previous = db.DB_PATH
        db.DB_PATH = self.path
        self.mode = patch.object(postgres, 'enabled', return_value=False)
        self.mode.start()
        db.init_db()
        roster = Path(self.temp.name) / 'roster.csv'
        roster.write_text('Iniziali;Codice\nAA;0123\n', encoding='utf-8')
        db.import_student_codes(roster)
        db.add_teacher('Test', 'Test')
        db.add_lesson(db.list_teachers()[0]['id'], '2026-11-10', 1, 'Test')
        db.add_vote(db.list_lessons()[0]['id'], '0123', 5)

    def tearDown(self):
        self.mode.stop()
        db.DB_PATH = self.previous
        self.temp.cleanup()

    def test_snapshot_preserves_key_ids_and_all_rows_without_changing_source(self):
        with db.connect() as con:
            before = migrate.read_rows(con)
        snapshot = migrate.read_sqlite(self.path)
        self.assertEqual(snapshot, before)
        with db.connect() as con:
            self.assertEqual(migrate.read_rows(con), before)

    def test_backup_round_trip(self):
        import json
        source = migrate.read_sqlite(self.path)
        backup = migrate.save_backup(source, self.temp.name)
        restored = json.loads(backup.read_text(encoding='utf-8'))
        self.assertEqual(restored['data'], source)
        migrate.validate(restored['data'])

    def test_orphaned_participation_is_rejected(self):
        data = migrate.read_sqlite(self.path)
        data['participation'][0][1] = '0' * 64
        with self.assertRaises(ValueError):
            migrate.validate(data)

    def test_unmatched_votes_are_rejected(self):
        data = migrate.read_sqlite(self.path)
        data['votes'] = []
        with self.assertRaises(ValueError):
            migrate.validate(data)

    def test_missing_key_is_rejected(self):
        data = migrate.read_sqlite(self.path)
        data['settings'] = [r for r in data['settings'] if r[0] != 'voter_key']
        with self.assertRaises(ValueError):
            migrate.validate(data)

    def test_missing_source_does_not_create_database(self):
        missing = Path(self.temp.name) / 'missing.sqlite3'
        with self.assertRaises(Exception):
            migrate.read_sqlite(missing)
        self.assertFalse(missing.exists())
