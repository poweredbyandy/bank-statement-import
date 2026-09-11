# Copyright 2026 andyengit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from base64 import b64encode
from os import path

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestStatementImportPreview(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.currency = cls.env.ref("base.USD")
        cls.currency.active = True
        cls.suspense_account = cls.env["account.account"].create(
            {
                "code": "PREV987",
                "name": "Preview Suspense",
                "account_type": "asset_current",
            }
        )
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Preview Bank",
                "type": "bank",
                "code": "PRVB",
                "currency_id": cls.currency.id,
                "suspense_account_id": cls.suspense_account.id,
            }
        )
        cls.Wizard = cls.env["account.statement.import"]
        cls.sample_path = path.join(
            path.dirname(__file__), "samples", "mayo_13_al_20.txt"
        )
        cls.mercantil_path = path.join(
            path.dirname(__file__), "samples", "mercantil_sample.txt"
        )

    def _wizard_from_file(self, filepath, filename):
        with open(filepath, "rb") as sample:
            data = b64encode(sample.read())
        return self.Wizard.with_context(
            journal_id=self.journal.id,
            account_statement_import_sheet_file_test=True,
        ).create(
            {
                "statement_filename": filename,
                "statement_file": data,
            }
        )

    def _wizard_from_sample(self):
        return self._wizard_from_file(self.sample_path, "mayo_13_al_20.txt")

    def test_auto_detect_tab_file(self):
        wizard = self._wizard_from_sample()
        wizard._auto_detect_and_preview()
        self.assertEqual(wizard.cfg_delimiter, "tab")
        self.assertEqual(wizard.cfg_timestamp_column, "Fecha")
        self.assertEqual(wizard.cfg_amount_column, "Monto")
        self.assertEqual(wizard.cfg_reference_column, "Referencia")
        self.assertEqual(wizard.cfg_description_column, "Descripción")
        self.assertEqual(wizard.cfg_balance_column, "Balance")
        self.assertEqual(wizard.cfg_file_encoding, "windows-1252")
        self.assertEqual(wizard.cfg_timestamp_format, "%d/%m/%Y")
        self.assertTrue(wizard.preview_json)
        self.assertGreater(wizard.preview_json.get("total_rows", 0), 0)
        self.assertGreater(wizard.preview_line_count, 0)
        self.assertFalse(wizard.preview_error)

    def test_autosave_mapping_links_journal(self):
        wizard = self._wizard_from_sample()
        wizard._auto_detect_and_preview()
        mapping = wizard._autosave_sheet_mapping(force=True)
        self.assertTrue(mapping)
        self.assertIn(mapping, self.journal.sheet_mapping_ids)
        self.assertEqual(self.journal.default_sheet_mapping_id, mapping)

    def test_import_sets_last_used_mapping(self):
        wizard = self._wizard_from_sample()
        wizard._auto_detect_and_preview()
        wizard.auto_save_mapping = True
        wizard.import_file_button()
        self.assertTrue(self.journal.default_sheet_mapping_id)
        self.assertTrue(self.journal.sheet_mapping_ids)
        statements = self.env["account.bank.statement"].search(
            [("journal_id", "=", self.journal.id)]
        )
        self.assertEqual(len(statements), 1)
        self.assertGreater(len(statements.line_ids), 10)

    def test_detect_mercantil_no_header(self):
        wizard = self._wizard_from_file(self.mercantil_path, "marzo.txt")
        wizard._auto_detect_and_preview()
        self.assertTrue(wizard.cfg_no_header)
        self.assertEqual(wizard.cfg_delimiter, "comma")
        self.assertEqual(wizard.cfg_timestamp_format, "%d%m%Y")
        self.assertEqual(wizard.cfg_timestamp_column, "3")
        self.assertEqual(wizard.cfg_reference_column, "4")
        self.assertEqual(wizard.cfg_debit_credit_column, "5")
        self.assertEqual(wizard.cfg_description_column, "6")
        self.assertEqual(wizard.cfg_amount_column, "7")
        self.assertEqual(wizard.cfg_balance_column, "8")
        self.assertEqual(wizard.cfg_amount_type, "absolute_value")
        self.assertEqual(wizard.cfg_debit_value, "ND")
        self.assertEqual(wizard.cfg_credit_value, "NC")
        self.assertFalse(wizard.preview_error)
        self.assertGreater(wizard.preview_line_count, 0)
        parsed = wizard.preview_json.get("parsed_lines") or []
        self.assertTrue(parsed)
        amounts = [line["amount"] for line in parsed if line.get("ref") == "02700416259"]
        self.assertTrue(amounts)
        self.assertLess(amounts[0], 0)

    def test_duplicate_reference_is_omitted(self):
        wizard = self._wizard_from_sample()
        wizard._auto_detect_and_preview()
        wizard.import_file_button()
        first_count = self.env["account.bank.statement.line"].search_count(
            [("journal_id", "=", self.journal.id)]
        )
        self.assertGreater(first_count, 0)

        wizard2 = self._wizard_from_sample()
        wizard2._auto_detect_and_preview()
        summary = wizard2.preview_json.get("summary") or {}
        self.assertGreater(summary.get("duplicate_count") or 0, 0)
        self.assertEqual(summary.get("new_count") or 0, 0)
        self.assertTrue(
            any(
                line.get("is_duplicate")
                for line in wizard2.preview_json.get("parsed_lines") or []
            )
        )

        with self.assertRaises(Exception):
            wizard2.import_file_button()
        second_count = self.env["account.bank.statement.line"].search_count(
            [("journal_id", "=", self.journal.id)]
        )
        self.assertEqual(first_count, second_count)

    def test_identical_sms_fees_are_imported_separately(self):
        sample = path.join(
            path.dirname(__file__), "samples", "sms_fees_duplicate.txt"
        )
        wizard = self._wizard_from_file(sample, "sms_fees_duplicate.txt")
        wizard._auto_detect_and_preview()
        self.assertFalse(wizard.preview_error)
        self.assertEqual(wizard.preview_line_count, 3)
        wizard.import_file_button()
        lines = self.env["account.bank.statement.line"].search(
            [("journal_id", "=", self.journal.id)], order="date, id"
        )
        self.assertEqual(len(lines), 3)
        sms = lines.filtered(lambda line: line.ref == "9640431072026")
        self.assertEqual(len(sms), 2)
        self.assertEqual(len(set(sms.mapped("unique_import_id"))), 2)
        self.assertTrue(all(line.amount == -8 for line in sms))
