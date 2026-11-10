import os
import unittest
from unittest.mock import patch

import postgres
import streamlit as st


class CloudSettingsTests(unittest.TestCase):
    def test_cloud_secrets_select_postgres_without_local_file(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(postgres.Path, 'exists', return_value=False), patch.object(st, 'secrets', {'DATABASE_URL': 'postgresql://cloud-placeholder'}):
            self.assertTrue(postgres.enabled())
            self.assertEqual(postgres.setting('DATABASE_URL'), 'postgresql://cloud-placeholder')

    def test_cloud_admin_pin_is_loaded(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(postgres.Path, 'exists', return_value=False), patch.object(st, 'secrets', {'ADMIN_PIN': 'test-only-pin'}):
            self.assertEqual(postgres.setting('ADMIN_PIN'), 'test-only-pin')

    def test_explicit_environment_overrides_cloud_secrets(self):
        with patch.dict(os.environ, {'DATABASE_URL': ''}, clear=True), patch.object(st, 'secrets', {'DATABASE_URL': 'postgresql://cloud-placeholder'}):
            self.assertFalse(postgres.enabled())
