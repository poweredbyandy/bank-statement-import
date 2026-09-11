# Copyright 2026 andyengit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    def _sheet_preview_normalize_ref(self, reference):
        return (reference or "").strip().lstrip("'").strip()

    def _sheet_preview_is_reliable_ref(self, reference):
        """Bank fees often reuse '0'; do not treat that as a unique key."""
        ref = self._sheet_preview_normalize_ref(reference)
        return bool(ref) and ref != "0"

    def _sheet_preview_existing_refs(self, journal):
        """Return normalized bank references already present on the journal."""
        if not journal:
            return set()
        refs = self.sudo().search_read(
            [
                ("journal_id", "=", journal.id),
                ("ref", "!=", False),
            ],
            ["ref"],
        )
        return {
            self._sheet_preview_normalize_ref(line["ref"])
            for line in refs
            if self._sheet_preview_is_reliable_ref(line.get("ref"))
        }
