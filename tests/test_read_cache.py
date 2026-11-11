"""Cache only public data, isolate databases and invalidate committed changes."""

from pathlib import Path
import unittest
from unittest.mock import patch

import database as db
import read_cache


class ReadCacheTests(unittest.TestCase):
    def setUp(self):
        self.backend = patch.object(db.postgres, 'enabled', return_value=False)
        self.backend.start()
        self.addCleanup(self.backend.stop)
        read_cache.clear()
        self.addCleanup(read_cache.clear)

    def test_reuses_public_statistics_and_returns_independent_copies(self):
        with patch.object(db, 'teacher_stats', return_value=[{'total_votes': 3}]) as query:
            first = read_cache.teacher_stats()
            first[0]['total_votes'] = 999
            self.assertEqual(read_cache.teacher_stats()[0]['total_votes'], 3)
            self.assertEqual(query.call_count, 1)

    def test_invalidating_reads_reveals_new_votes_and_history(self):
        with patch.object(db, 'teacher_stats', side_effect=[[{'total_votes': 3}], [{'total_votes': 4}]]), patch.object(db, 'subject_history', side_effect=[[{'average_rating': 3}], [{'average_rating': 4}]]):
            self.assertEqual(read_cache.teacher_stats()[0]['total_votes'], 3)
            self.assertEqual(read_cache.subject_history('Math')[0]['average_rating'], 3)
            read_cache.clear()
            self.assertEqual(read_cache.teacher_stats()[0]['total_votes'], 4)
            self.assertEqual(read_cache.subject_history('Math')[0]['average_rating'], 4)

    def test_cache_is_separate_for_each_database(self):
        with patch.object(db, 'teacher_stats', side_effect=[[{'total_votes': 3}], [{'total_votes': 8}]]):
            with patch.object(db, 'DB_PATH', Path('cache-test-one.sqlite3')):
                self.assertEqual(read_cache.teacher_stats()[0]['total_votes'], 3)
            with patch.object(db, 'DB_PATH', Path('cache-test-two.sqlite3')):
                self.assertEqual(read_cache.teacher_stats()[0]['total_votes'], 8)

    def test_history_keeps_subject_and_threshold_separate(self):
        with patch.object(db, 'subject_history', side_effect=[['math'], ['history'], ['math-strict']]) as query:
            self.assertEqual(read_cache.subject_history('Math', 3), ['math'])
            self.assertEqual(read_cache.subject_history('History', 3), ['history'])
            self.assertEqual(read_cache.subject_history('Math', 5), ['math-strict'])
            self.assertEqual(read_cache.subject_history('Math', 3), ['math'])
            self.assertEqual(query.call_count, 3)
