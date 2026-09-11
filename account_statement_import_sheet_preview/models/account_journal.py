# Copyright 2026 andyengit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    sheet_mapping_ids = fields.Many2many(
        comodel_name="account.statement.import.sheet.mapping",
        relation="account_journal_sheet_mapping_rel",
        column1="journal_id",
        column2="mapping_id",
        string="Statement Sheet Mappings",
        help="Mappings available for this journal when importing TXT/CSV/XLSX files.",
    )

    def _statement_line_import_update_unique_import_id(
        self, st_line_vals, account_number
    ):
        Line = self.env["account.bank.statement.line"]
        payment_ref = (st_line_vals.get("payment_ref") or "").strip()
        balance = st_line_vals.pop("_sheet_balance", None)
        if not st_line_vals.get("unique_import_id"):
            ref = Line._sheet_preview_normalize_ref(st_line_vals.get("ref"))
            if ref:
                date_value = st_line_vals.get("date") or ""
                amount = st_line_vals.get("amount") or ""
                parts = ["ref:%s" % ref, str(date_value), str(amount), payment_ref]
                if balance is not None:
                    parts.append(str(balance))
                st_line_vals["unique_import_id"] = ":".join(parts)
        elif payment_ref:
            uid = st_line_vals["unique_import_id"]
            if payment_ref not in uid:
                st_line_vals["unique_import_id"] = f"{uid}:{payment_ref}"
            if balance is not None:
                uid = st_line_vals["unique_import_id"]
                if str(balance) not in uid:
                    st_line_vals["unique_import_id"] = f"{uid}:{balance}"
        return super()._statement_line_import_update_unique_import_id(
            st_line_vals, account_number
        )

    @api.model_create_multi
    def create(self, vals_list):
        journals = super().create(vals_list)
        for journal in journals:
            journal._ensure_default_sheet_mapping_in_list()
        return journals

    def write(self, vals):
        res = super().write(vals)
        if "default_sheet_mapping_id" in vals or "sheet_mapping_ids" in vals:
            self._ensure_default_sheet_mapping_in_list()
        return res

    def _ensure_default_sheet_mapping_in_list(self):
        for journal in self:
            mapping = journal.default_sheet_mapping_id
            if mapping and mapping not in journal.sheet_mapping_ids:
                journal.sudo().write({"sheet_mapping_ids": [(4, mapping.id)]})

    def _set_last_sheet_mapping(self, mapping):
        self.ensure_one()
        if not mapping:
            return
        vals = {"default_sheet_mapping_id": mapping.id}
        if mapping not in self.sheet_mapping_ids:
            vals["sheet_mapping_ids"] = [(4, mapping.id)]
        self.sudo().write(vals)
