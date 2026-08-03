# Copyright 2026 andyengit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import logging
import re
from collections import Counter
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import chardet
except ImportError:  # pragma: no cover
    chardet = None

DELIMITER_CANDIDATES = [
    ("semicolon", ";"),
    ("comma", ","),
    ("tab", "\t"),
    ("space", " "),
]

DATE_FORMAT_CANDIDATES = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%y",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%d%m%Y",
]

MERCANTIL_SIGN_CODES = {"ND", "NC", "SI", "AC", "DP"}

COLUMN_ALIASES = {
    "timestamp_column": [
        "fecha",
        "date",
        "fecha valor",
        "fecha operacion",
        "fecha operación",
        "transaction date",
        "booking date",
    ],
    "amount_column": [
        "monto",
        "amount",
        "importe",
        "cantidad",
        "monto bs",
        "monto bs.",
        "valor",
    ],
    "balance_column": [
        "balance",
        "saldo",
        "saldo disponible",
        "running balance",
    ],
    "reference_column": [
        "referencia",
        "reference",
        "ref",
        "nro referencia",
        "numero referencia",
        "número referencia",
    ],
    "description_column": [
        "descripcion",
        "descripción",
        "description",
        "concepto",
        "detalle",
        "narration",
        "memo",
        "descripcion de la transaccion",
        "descripción de la transacción",
    ],
    "partner_name_column": [
        "beneficiario",
        "partner",
        "nombre",
        "payee",
    ],
    "transaction_id_column": [
        "id",
        "transaction id",
        "unique id",
        "nro operacion",
        "número operación",
    ],
    "amount_debit_column": [
        "debito",
        "débito",
        "debit",
        "cargos",
        "retiro",
    ],
    "amount_credit_column": [
        "credito",
        "crédito",
        "credit",
        "abonos",
        "deposito",
        "depósito",
    ],
    "debit_credit_column": [
        "tipo",
        "d/c",
        "debit/credit",
        "signo",
    ],
}

EXACT_ONLY_ALIASES = {
    "tipo",
    "id",
    "ref",
    "date",
    "signo",
    "valor",
}

COLUMN_CFG_FIELDS = [
    "cfg_timestamp_column",
    "cfg_amount_column",
    "cfg_amount_debit_column",
    "cfg_amount_credit_column",
    "cfg_debit_credit_column",
    "cfg_balance_column",
    "cfg_description_column",
    "cfg_reference_column",
    "cfg_notes_column",
    "cfg_partner_name_column",
    "cfg_transaction_id_column",
    "cfg_currency_column",
    "cfg_bank_account_column",
    "cfg_bank_name_column",
]

MAPPING_SYNC_FIELDS = [
    "delimiter",
    "file_encoding",
    "quotechar",
    "timestamp_format",
    "float_thousands_sep",
    "float_decimal_sep",
    "no_header",
    "header_lines_skip_count",
    "footer_lines_skip_count",
    "offset_column",
    "skip_empty_lines",
    "amount_type",
    "amount_inverse_sign",
    "timestamp_column",
    "amount_column",
    "amount_debit_column",
    "amount_credit_column",
    "debit_credit_column",
    "debit_value",
    "credit_value",
    "balance_column",
    "description_column",
    "reference_column",
    "notes_column",
    "partner_name_column",
    "transaction_id_column",
    "currency_column",
    "bank_account_column",
    "bank_name_column",
]


class AccountStatementImport(models.TransientModel):
    _inherit = "account.statement.import"

    sheet_mapping_id = fields.Many2one(
        string="Formato guardado",
        comodel_name="account.statement.import.sheet.mapping",
        default=lambda self: self._get_default_mapping_id(),
        help="Elija un formato ya guardado para este diario, o deje que Odoo detecte uno nuevo.",
    )
    allowed_sheet_mapping_ids = fields.Many2many(
        comodel_name="account.statement.import.sheet.mapping",
        compute="_compute_allowed_sheet_mapping_ids",
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        compute="_compute_journal_id",
    )
    auto_save_mapping = fields.Boolean(
        string="Recordar este formato la próxima vez",
        default=True,
        help="Guarda el formato detectado en este diario para facilitar la próxima importación.",
    )
    mapping_name = fields.Char(
        string="Nombre del formato",
        help="Un nombre sencillo para reconocer este formato de archivo del banco.",
    )
    show_advanced_options = fields.Boolean(
        string="Mostrar opciones avanzadas",
        help="Solo necesario si la detección automática no funcionó bien.",
    )
    preview_json = fields.Json(string="Preview data")
    preview_message = fields.Char(string="Estado", readonly=True)
    preview_help = fields.Char(
        string="Qué hacer ahora",
        readonly=True,
    )
    preview_state = fields.Selection(
        selection=[
            ("empty", "Esperando archivo"),
            ("ready", "Listo para importar"),
            ("warning", "Revisar"),
            ("error", "Corregir"),
        ],
        default="empty",
        readonly=True,
    )
    preview_line_count = fields.Integer(readonly=True)
    preview_error = fields.Char(readonly=True)

    cfg_delimiter = fields.Selection(
        selection=[
            ("dot", "dot (.)"),
            ("comma", "comma (,)"),
            ("semicolon", "semicolon (;)"),
            ("tab", "tab"),
            ("space", "space"),
            ("n/a", "N/A (XLSX)"),
        ],
        string="Delimiter",
        default="comma",
    )
    cfg_file_encoding = fields.Selection(
        selection=[
            ("utf-8", "UTF-8"),
            ("utf-8-sig", "UTF-8 (with BOM)"),
            ("windows-1252", "Western (Windows-1252)"),
            ("iso-8859-1", "Western (Latin-1 / ISO 8859-1)"),
        ],
        string="Encoding",
        default="utf-8",
    )
    cfg_quotechar = fields.Char(string="Text qualifier", size=1, default='"')
    cfg_timestamp_format = fields.Char(string="Date format", default="%d/%m/%Y")
    cfg_float_thousands_sep = fields.Selection(
        selection=[
            ("dot", "dot (.)"),
            ("comma", "comma (,)"),
            ("quote", "quote (')"),
            ("none", "none"),
        ],
        string="Thousands Separator",
        default="dot",
    )
    cfg_float_decimal_sep = fields.Selection(
        selection=[
            ("dot", "dot (.)"),
            ("comma", "comma (,)"),
            ("none", "none"),
        ],
        string="Decimals Separator",
        default="comma",
    )
    cfg_no_header = fields.Boolean(string="No header line")
    cfg_header_lines_skip_count = fields.Integer(string="Header lines skip", default=0)
    cfg_footer_lines_skip_count = fields.Integer(string="Footer lines skip", default=0)
    cfg_offset_column = fields.Integer(string="Offset column", default=0)
    cfg_skip_empty_lines = fields.Boolean(string="Skip empty lines", default=True)
    cfg_amount_type = fields.Selection(
        selection=[
            ("simple_value", "Simple value"),
            ("absolute_value", "Absolute value"),
            ("distinct_credit_debit", "Distinct Credit/debit Column"),
        ],
        string="Amount type",
        default="simple_value",
    )
    cfg_amount_inverse_sign = fields.Boolean(string="Inverse sign of amount")
    cfg_timestamp_column = fields.Char(string="Date column")
    cfg_amount_column = fields.Char(string="Amount column")
    cfg_amount_debit_column = fields.Char(string="Debit amount column")
    cfg_amount_credit_column = fields.Char(string="Credit amount column")
    cfg_debit_credit_column = fields.Char(string="Debit/credit column")
    cfg_debit_value = fields.Char(default="D")
    cfg_credit_value = fields.Char(default="C")
    cfg_balance_column = fields.Char(string="Balance column")
    cfg_description_column = fields.Char(string="Description column")
    cfg_reference_column = fields.Char(string="Reference column")
    cfg_notes_column = fields.Char(string="Notes column")
    cfg_partner_name_column = fields.Char(string="Partner name column")
    cfg_transaction_id_column = fields.Char(string="Transaction ID column")
    cfg_currency_column = fields.Char(string="Currency column")
    cfg_bank_account_column = fields.Char(string="Bank account column")
    cfg_bank_name_column = fields.Char(string="Bank name column")

    @api.depends_context("journal_id")
    def _compute_journal_id(self):
        journal = self.env["account.journal"].browse(self.env.context.get("journal_id"))
        for wizard in self:
            wizard.journal_id = journal

    @api.depends_context("journal_id")
    def _compute_allowed_sheet_mapping_ids(self):
        Mapping = self.env["account.statement.import.sheet.mapping"]
        journal = self.env["account.journal"].browse(self.env.context.get("journal_id"))
        for wizard in self:
            if journal and journal.sheet_mapping_ids:
                wizard.allowed_sheet_mapping_ids = journal.sheet_mapping_ids
            else:
                wizard.allowed_sheet_mapping_ids = Mapping.search([])

    def _get_default_mapping_id(self):
        journal = self.env["account.journal"].browse(self.env.context.get("journal_id"))
        if journal.default_sheet_mapping_id:
            return journal.default_sheet_mapping_id
        if journal.sheet_mapping_ids:
            return journal.sheet_mapping_ids[:1]
        return super()._get_default_mapping_id()

    @api.onchange("sheet_mapping_id")
    def _onchange_sheet_mapping_id(self):
        if self.sheet_mapping_id:
            self._load_mapping_to_cfg(self.sheet_mapping_id)
            if self.statement_file:
                self._refresh_preview_data()

    @api.onchange("statement_file", "statement_filename")
    def _onchange_statement_file_preview(self):
        if not self.statement_file:
            self.preview_json = False
            self.preview_message = self.env._(
                "Suba el archivo del banco para continuar."
            )
            self.preview_help = self.env._(
                "Archivos aceptados: TXT, CSV o Excel (XLSX)."
            )
            self.preview_error = False
            self.preview_line_count = 0
            self.preview_state = "empty"
            return
        self._auto_detect_and_preview()

    @api.onchange(
        "cfg_delimiter",
        "cfg_file_encoding",
        "cfg_quotechar",
        "cfg_timestamp_format",
        "cfg_float_thousands_sep",
        "cfg_float_decimal_sep",
        "cfg_no_header",
        "cfg_header_lines_skip_count",
        "cfg_footer_lines_skip_count",
        "cfg_offset_column",
        "cfg_skip_empty_lines",
        "cfg_amount_type",
        "cfg_amount_inverse_sign",
        "cfg_timestamp_column",
        "cfg_amount_column",
        "cfg_amount_debit_column",
        "cfg_amount_credit_column",
        "cfg_debit_credit_column",
        "cfg_debit_value",
        "cfg_credit_value",
        "cfg_balance_column",
        "cfg_description_column",
        "cfg_reference_column",
        "cfg_notes_column",
        "cfg_partner_name_column",
        "cfg_transaction_id_column",
        "cfg_currency_column",
        "cfg_bank_account_column",
        "cfg_bank_name_column",
    )
    def _onchange_cfg_preview(self):
        if self.statement_file:
            self._refresh_preview_data()

    def action_refresh_preview(self):
        self.ensure_one()
        if not self.statement_file:
            raise UserError(self.env._("Primero suba un archivo de extracto."))
        self._refresh_preview_data()
        if self.auto_save_mapping and not self.preview_error:
            self._autosave_sheet_mapping()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": self.env.context,
        }

    def action_save_mapping(self):
        self.ensure_one()
        mapping = self._autosave_sheet_mapping(force=True)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Formato guardado"),
                "message": self.env._(
                    "El formato '%s' se guardó y quedó vinculado al diario.",
                    mapping.display_name,
                ),
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.act_window",
                    "res_model": self._name,
                    "res_id": self.id,
                    "view_mode": "form",
                    "target": "new",
                    "context": self.env.context,
                },
            },
        }

    def import_file_button(self):
        self.ensure_one()
        file_data = self._get_file_data() if self.statement_file else b""
        use_sheet = bool(self.statement_file) and self._seems_sheet_file(file_data)
        if use_sheet and (
            self.auto_save_mapping
            or not self.sheet_mapping_id
            or self.cfg_timestamp_column
        ):
            self._autosave_sheet_mapping(force=True)
        action = super().import_file_button()
        journal = self.journal_id
        if use_sheet and journal and self.sheet_mapping_id:
            journal._set_last_sheet_mapping(self.sheet_mapping_id)
        return action

    def _parse_file(self, data_file):
        if self.sheet_mapping_id and not self._seems_sheet_file(data_file):
            mapping = self.sheet_mapping_id
            self.sheet_mapping_id = False
            try:
                return super()._parse_file(data_file)
            finally:
                self.sheet_mapping_id = mapping
        return super()._parse_file(data_file)

    def _create_bank_statements(self, stmts_vals, result):
        omitted = []
        Line = self.env["account.bank.statement.line"]
        existing_refs = Line._sheet_preview_existing_refs(self.journal_id)
        for st_vals in stmts_vals:
            kept = []
            for lvals in st_vals.get("transactions") or []:
                ref = Line._sheet_preview_normalize_ref(lvals.get("ref"))
                if (
                    Line._sheet_preview_is_reliable_ref(ref)
                    and ref in existing_refs
                ):
                    omitted.append(lvals)
                    if "balance_start" in st_vals:
                        st_vals["balance_start"] += float(lvals["amount"])
                else:
                    kept.append(lvals)
            st_vals["transactions"] = kept
        res = super()._create_bank_statements(stmts_vals, result)
        if omitted:
            refs = sorted(
                {
                    Line._sheet_preview_normalize_ref(line.get("ref"))
                    for line in omitted
                    if Line._sheet_preview_is_reliable_ref(line.get("ref"))
                }
            )
            if len(omitted) == 1:
                msg = self.env._(
                    "1 movimiento con referencia ya existente se omitirá: %s",
                    refs[0] if refs else "",
                )
            else:
                sample = ", ".join(refs[:8])
                if len(refs) > 8:
                    sample = f"{sample}..."
                msg = self.env._(
                    "%(count)s movimientos con referencia ya existente se omitirán"
                    " (%(refs)s).",
                    count=len(omitted),
                    refs=sample,
                )
            result.setdefault("notifications", []).append(msg)
        return res

    def _seems_sheet_file(self, data_file):
        filename = (self.statement_filename or "").lower()
        if filename.endswith((".csv", ".txt", ".xlsx", ".xls")):
            return True
        if filename.endswith((".ofx", ".qif", ".xml", ".camt")):
            return False
        if data_file[:2] == b"PK":
            return True
        head = data_file[:128].lstrip().upper()
        if head.startswith((b"OFX", b"OFXHEADER", b"<?XML", b"<OFX")):
            return False
        return bool(self.cfg_timestamp_column or self.cfg_delimiter == "n/a")

    def _get_file_data(self):
        self.ensure_one()
        return base64.b64decode(self.statement_file)

    def _load_mapping_to_cfg(self, mapping):
        self.mapping_name = mapping.name
        self.cfg_delimiter = mapping.delimiter
        self.cfg_file_encoding = mapping.file_encoding
        self.cfg_quotechar = mapping.quotechar or '"'
        self.cfg_timestamp_format = mapping.timestamp_format
        self.cfg_float_thousands_sep = mapping.float_thousands_sep
        self.cfg_float_decimal_sep = mapping.float_decimal_sep
        self.cfg_no_header = mapping.no_header
        self.cfg_header_lines_skip_count = mapping.header_lines_skip_count
        self.cfg_footer_lines_skip_count = mapping.footer_lines_skip_count
        self.cfg_offset_column = mapping.offset_column
        self.cfg_skip_empty_lines = mapping.skip_empty_lines
        self.cfg_amount_type = mapping.amount_type
        self.cfg_amount_inverse_sign = mapping.amount_inverse_sign
        self.cfg_timestamp_column = mapping.timestamp_column
        self.cfg_amount_column = mapping.amount_column
        self.cfg_amount_debit_column = mapping.amount_debit_column
        self.cfg_amount_credit_column = mapping.amount_credit_column
        self.cfg_debit_credit_column = mapping.debit_credit_column
        self.cfg_debit_value = mapping.debit_value
        self.cfg_credit_value = mapping.credit_value
        self.cfg_balance_column = mapping.balance_column
        self.cfg_description_column = mapping.description_column
        self.cfg_reference_column = mapping.reference_column
        self.cfg_notes_column = mapping.notes_column
        self.cfg_partner_name_column = mapping.partner_name_column
        self.cfg_transaction_id_column = mapping.transaction_id_column
        self.cfg_currency_column = mapping.currency_column
        self.cfg_bank_account_column = mapping.bank_account_column
        self.cfg_bank_name_column = mapping.bank_name_column

    def _cfg_to_mapping_vals(self):
        self.ensure_one()
        name = self.mapping_name or self._default_mapping_name()
        vals = {
            "name": name,
            "delimiter": self.cfg_delimiter or "comma",
            "file_encoding": self.cfg_file_encoding or "utf-8",
            "quotechar": self.cfg_quotechar or '"',
            "timestamp_format": self.cfg_timestamp_format or "%d/%m/%Y",
            "float_thousands_sep": self.cfg_float_thousands_sep or "dot",
            "float_decimal_sep": self.cfg_float_decimal_sep or "comma",
            "no_header": bool(self.cfg_no_header),
            "header_lines_skip_count": self.cfg_header_lines_skip_count or 0,
            "footer_lines_skip_count": self.cfg_footer_lines_skip_count or 0,
            "offset_column": self.cfg_offset_column or 0,
            "skip_empty_lines": bool(self.cfg_skip_empty_lines),
            "amount_type": self.cfg_amount_type or "simple_value",
            "amount_inverse_sign": bool(self.cfg_amount_inverse_sign),
            "timestamp_column": self.cfg_timestamp_column or "0",
            "amount_column": self.cfg_amount_column,
            "amount_debit_column": self.cfg_amount_debit_column,
            "amount_credit_column": self.cfg_amount_credit_column,
            "debit_credit_column": self.cfg_debit_credit_column,
            "debit_value": self.cfg_debit_value or "D",
            "credit_value": self.cfg_credit_value or "C",
            "balance_column": self.cfg_balance_column,
            "description_column": self.cfg_description_column,
            "reference_column": self.cfg_reference_column,
            "notes_column": self.cfg_notes_column,
            "partner_name_column": self.cfg_partner_name_column,
            "transaction_id_column": self.cfg_transaction_id_column,
            "currency_column": self.cfg_currency_column,
            "bank_account_column": self.cfg_bank_account_column,
            "bank_name_column": self.cfg_bank_name_column,
        }
        return vals

    def _default_mapping_name(self):
        journal = self.journal_id
        filename = self.statement_filename or self.env._("Statement")
        journal_name = journal.display_name if journal else self.env._("Journal")
        return self.env._(
            "Auto: %(journal)s - %(filename)s", journal=journal_name, filename=filename
        )

    def _mapping_fingerprint(self, vals):
        return tuple(vals.get(field) for field in MAPPING_SYNC_FIELDS)

    def _find_matching_mapping(self, vals):
        Mapping = self.env["account.statement.import.sheet.mapping"]
        journal = self.journal_id
        candidates = journal.sheet_mapping_ids if journal else Mapping.browse()
        if not candidates:
            candidates = Mapping.search([])
        fingerprint = self._mapping_fingerprint(vals)
        for mapping in candidates:
            current = {field: mapping[field] for field in MAPPING_SYNC_FIELDS}
            if self._mapping_fingerprint(current) == fingerprint:
                return mapping
        return Mapping.browse()

    def _autosave_sheet_mapping(self, force=False):
        self.ensure_one()
        if not force and not self.auto_save_mapping:
            return self.sheet_mapping_id
        vals = self._cfg_to_mapping_vals()
        if not vals.get("timestamp_column"):
            raise UserError(self.env._("Indique la columna de fecha antes de guardar."))
        if vals["amount_type"] == "simple_value" and not vals.get("amount_column"):
            raise UserError(self.env._("Indique la columna de monto antes de guardar."))
        if vals["amount_type"] == "absolute_value" and not vals.get(
            "debit_credit_column"
        ):
            raise UserError(
                self.env._("Indique la columna de débito/crédito antes de guardar.")
            )
        if vals["amount_type"] == "distinct_credit_debit" and (
            not vals.get("amount_debit_column") or not vals.get("amount_credit_column")
        ):
            raise UserError(
                self.env._("Indique las columnas de débito y crédito antes de guardar.")
            )

        mapping = self.sheet_mapping_id
        matching = self._find_matching_mapping(vals)
        if matching:
            mapping = matching
            mapping.write({"name": vals["name"]})
        elif mapping:
            mapping.write(vals)
        else:
            mapping = self.env["account.statement.import.sheet.mapping"].create(vals)

        self.sheet_mapping_id = mapping
        self.mapping_name = mapping.name
        journal = self.journal_id
        if journal:
            journal._set_last_sheet_mapping(mapping)
        return mapping

    def _clear_column_cfg(self):
        for field_name in COLUMN_CFG_FIELDS:
            setattr(self, field_name, False)
        self.cfg_debit_value = "D"
        self.cfg_credit_value = "C"
        self.cfg_amount_type = "simple_value"
        self.cfg_header_lines_skip_count = 0
        self.cfg_no_header = False

    def _iter_candidate_mappings(self):
        seen = set()
        for mapping in [self.sheet_mapping_id] + list(
            self.journal_id.sheet_mapping_ids if self.journal_id else []
        ):
            if not mapping or mapping.id in seen:
                continue
            seen.add(mapping.id)
            yield mapping

    def _try_existing_mappings(self, data_file):
        Parser = self.env["account.statement.import.sheet.parser"]
        filename = self.statement_filename or "statement.xlsx"
        for mapping in self._iter_candidate_mappings():
            parsed = Parser.get_parsed_preview(data_file, mapping, filename, limit=5)
            if not parsed.get("error") and parsed.get("line_count"):
                return mapping
        return self.env["account.statement.import.sheet.mapping"]

    def _auto_detect_and_preview(self):
        data_file = self._get_file_data()
        filename = (self.statement_filename or "").lower()
        working = self._try_existing_mappings(data_file)
        if working:
            self.sheet_mapping_id = working
            self._load_mapping_to_cfg(working)
            self._refresh_preview_data()
            return
        self._clear_column_cfg()
        detected = self._detect_file_settings(data_file, filename)
        for key, value in detected.items():
            setattr(self, key, value)
        if not self.mapping_name:
            self.mapping_name = self._default_mapping_name()
        vals = self._cfg_to_mapping_vals()
        matching = self._find_matching_mapping(vals)
        if matching:
            self.sheet_mapping_id = matching
            self.mapping_name = matching.name
            self._load_mapping_to_cfg(matching)
        self._refresh_preview_data()

    def _detect_file_settings(self, data_file, filename):
        result = {
            "cfg_quotechar": '"',
            "cfg_skip_empty_lines": True,
            "cfg_header_lines_skip_count": 0,
            "cfg_footer_lines_skip_count": 0,
            "cfg_offset_column": 0,
            "cfg_no_header": False,
            "cfg_amount_type": "simple_value",
            "cfg_amount_inverse_sign": False,
        }
        for field_name in COLUMN_CFG_FIELDS:
            result[field_name] = False
        if filename.endswith((".xlsx", ".xls")):
            result["cfg_delimiter"] = "n/a"
            result["cfg_file_encoding"] = "utf-8"
        else:
            encoding = self._detect_encoding(data_file)
            result["cfg_file_encoding"] = encoding
            try:
                text = data_file.decode(encoding)
            except UnicodeDecodeError:
                text = data_file.decode(encoding, errors="replace")
            delimiter_key = self._detect_delimiter(text)
            result["cfg_delimiter"] = delimiter_key

        Parser = self.env["account.statement.import.sheet.parser"]
        raw_all = Parser.get_raw_preview(
            data_file,
            delimiter=result.get("cfg_delimiter", "comma"),
            file_encoding=result.get("cfg_file_encoding", "utf-8"),
            quotechar='"',
            header_lines_skip_count=0,
            no_header=True,
            offset_column=0,
            limit=60,
            skip_empty_lines=False,
        )
        if raw_all.get("is_xlsx"):
            result["cfg_delimiter"] = "n/a"
        all_rows = raw_all.get("rows") or []
        header_index = self._find_header_row_index(all_rows)
        if header_index is not None:
            skip_count = 0 if header_index == 0 else header_index + 1
            result["cfg_header_lines_skip_count"] = skip_count
            result["cfg_no_header"] = False
            columns = [
                value if value else f"Column {index}"
                for index, value in enumerate(all_rows[header_index])
            ]
            rows = [row for row in all_rows[header_index + 1 :] if any(row)][:30]
            mapped_columns = self._suggest_columns(columns)
            has_header = True
            result.update(mapped_columns)
        else:
            raw = Parser.get_raw_preview(
                data_file,
                delimiter=result.get("cfg_delimiter", "comma"),
                file_encoding=result.get("cfg_file_encoding", "utf-8"),
                quotechar='"',
                header_lines_skip_count=0,
                no_header=False,
                offset_column=0,
                limit=30,
            )
            columns = raw.get("columns") or []
            rows = raw.get("rows") or []
            mapped_columns = self._suggest_columns(columns)
            has_header = self._row_looks_like_header(columns, mapped_columns)
            if not has_header and result.get("cfg_delimiter") != "n/a":
                result["cfg_no_header"] = True
                raw = Parser.get_raw_preview(
                    data_file,
                    delimiter=result.get("cfg_delimiter", "comma"),
                    file_encoding=result.get("cfg_file_encoding", "utf-8"),
                    quotechar='"',
                    header_lines_skip_count=0,
                    no_header=True,
                    offset_column=0,
                    limit=30,
                )
                columns = raw.get("columns") or []
                rows = raw.get("rows") or []
                no_header_layout = self._suggest_no_header_columns(rows)
                if no_header_layout:
                    result.update(no_header_layout)
                    mapped_columns = {
                        key: value
                        for key, value in no_header_layout.items()
                        if key.startswith("cfg_") and key.endswith("_column")
                    }
                else:
                    mapped_columns = {}
            else:
                result["cfg_no_header"] = False
                result.update(mapped_columns)
        if mapped_columns.get("cfg_amount_debit_column") and mapped_columns.get(
            "cfg_amount_credit_column"
        ):
            result["cfg_amount_type"] = "distinct_credit_debit"
        elif mapped_columns.get("cfg_debit_credit_column"):
            result["cfg_amount_type"] = "absolute_value"
            debit_value, credit_value = self._detect_debit_credit_values(
                rows, columns, mapped_columns.get("cfg_debit_credit_column")
            )
            result["cfg_debit_value"] = debit_value
            result["cfg_credit_value"] = credit_value
        else:
            result["cfg_amount_type"] = "simple_value"
        date_format, thousands, decimals = self._detect_number_and_date(
            columns, rows, mapped_columns
        )
        if has_header or not result.get("cfg_timestamp_format"):
            result["cfg_timestamp_format"] = date_format
        if has_header or not result.get("cfg_float_thousands_sep"):
            result["cfg_float_thousands_sep"] = thousands
        if has_header or not result.get("cfg_float_decimal_sep"):
            result["cfg_float_decimal_sep"] = decimals
        return result

    def _find_header_row_index(self, rows):
        best_index = None
        best_score = 0
        for index, row in enumerate(rows[:40]):
            if not any(row):
                continue
            mapped = self._suggest_columns(row)
            score = 0
            if mapped.get("cfg_timestamp_column"):
                score += 3
            if mapped.get("cfg_amount_column") or (
                mapped.get("cfg_amount_debit_column")
                and mapped.get("cfg_amount_credit_column")
            ):
                score += 3
            if mapped.get("cfg_reference_column"):
                score += 1
            if mapped.get("cfg_description_column"):
                score += 1
            if mapped.get("cfg_debit_credit_column"):
                score += 1
            if mapped.get("cfg_balance_column"):
                score += 1
            if score >= 6 and score > best_score:
                best_index = index
                best_score = score
        return best_index

    def _detect_debit_credit_values(self, rows, columns, column_name):
        idx = self._get_column_index(columns, column_name)
        values = set()
        if idx is not None:
            for row in rows[:30]:
                if idx < len(row) and row[idx]:
                    values.add(str(row[idx]).strip().upper())
        if "ND" in values and "NC" in values:
            return "ND", "NC"
        if "D" in values and "C" in values:
            return "D", "C"
        return "D", "C"

    def _detect_encoding(self, data_file):
        for encoding in ("utf-8", "utf-8-sig", "windows-1252", "iso-8859-1"):
            try:
                data_file.decode(encoding)
                return encoding
            except UnicodeDecodeError:
                continue
        if chardet:
            detected = chardet.detect(data_file).get("encoding")
            if detected:
                return detected.lower().replace("utf8", "utf-8")
        return "utf-8"

    def _detect_delimiter(self, text):
        sample_lines = [line for line in text.splitlines() if line.strip()][:10]
        if not sample_lines:
            return "comma"
        scores = {}
        for key, char in DELIMITER_CANDIDATES:
            counts = [line.count(char) for line in sample_lines]
            if not counts or max(counts) == 0:
                continue
            most_common = Counter(counts).most_common(1)[0]
            if most_common[0] == 0:
                continue
            consistency = most_common[1] / len(counts)
            scores[key] = (most_common[0], consistency)
        if not scores:
            return "comma"
        return max(scores.items(), key=lambda item: (item[1][1], item[1][0]))[0]

    def _normalize_header(self, value):
        value = (value or "").strip().lower()
        value = (
            value.replace("á", "a")
            .replace("é", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("ú", "u")
        )
        value = re.sub(r"\s+", " ", value)
        return value.rstrip(".")

    def _header_matches_alias(self, header, aliases):
        if not header:
            return False
        if header in aliases:
            return True
        for alias in aliases:
            if alias in EXACT_ONLY_ALIASES or len(alias) <= 3:
                continue
            if alias in header:
                return True
        return False

    def _suggest_columns(self, columns):
        result = {}
        normalized = {
            index: self._normalize_header(column)
            for index, column in enumerate(columns)
        }
        used = set()
        for field_name, aliases in COLUMN_ALIASES.items():
            for index, header in normalized.items():
                if index in used:
                    continue
                if self._header_matches_alias(header, aliases):
                    result[f"cfg_{field_name}"] = columns[index]
                    used.add(index)
                    break
        return result

    def _row_looks_like_header(self, columns, mapped_columns):
        if mapped_columns.get("cfg_timestamp_column") or mapped_columns.get(
            "cfg_amount_column"
        ):
            return True
        data_like = 0
        for column in columns[:10]:
            value = (column or "").strip()
            if not value:
                continue
            if (
                re.fullmatch(r"\d+", value)
                or self._detect_date_format(value)
                or re.search(r"\d+[.,]\d+", value)
                or value.upper() in MERCANTIL_SIGN_CODES
                or value.upper() in {"VEB", "VES", "USD", "EUR", "USDT"}
            ):
                data_like += 1
        if data_like >= 3:
            return False
        for column in columns:
            normalized = self._normalize_header(column)
            for aliases in COLUMN_ALIASES.values():
                if self._header_matches_alias(normalized, aliases):
                    return True
        return False

    def _suggest_no_header_columns(self, rows):
        sample = [row for row in rows if any(row)][:10]
        if not sample:
            return {}
        if self._rows_match_mercantil_layout(sample):
            return {
                "cfg_timestamp_column": "3",
                "cfg_reference_column": "4",
                "cfg_debit_credit_column": "5",
                "cfg_description_column": "6",
                "cfg_amount_column": "7",
                "cfg_balance_column": "8",
                "cfg_amount_type": "absolute_value",
                "cfg_debit_value": "ND",
                "cfg_credit_value": "NC",
                "cfg_timestamp_format": "%d%m%Y",
                "cfg_float_thousands_sep": "dot",
                "cfg_float_decimal_sep": "comma",
                "cfg_delimiter": "comma",
                "cfg_quotechar": '"',
            }
        if self._rows_match_bancaribe_layout(sample):
            return {
                "cfg_timestamp_column": "0",
                "cfg_reference_column": "1",
                "cfg_description_column": "2",
                "cfg_debit_credit_column": "3",
                "cfg_amount_column": "4",
                "cfg_balance_column": "6",
                "cfg_amount_type": "absolute_value",
                "cfg_debit_value": "D",
                "cfg_credit_value": "C",
                "cfg_timestamp_format": "%d/%m/%Y",
                "cfg_float_thousands_sep": "dot",
                "cfg_float_decimal_sep": "comma",
            }
        return {}

    def _rows_match_mercantil_layout(self, rows):
        matches = 0
        for row in rows:
            if len(row) < 9:
                continue
            date_value = (row[3] or "").strip()
            sign_value = (row[5] or "").strip().upper()
            amount_value = (row[7] or "").strip()
            if (
                re.fullmatch(r"\d{8}", date_value)
                and sign_value in MERCANTIL_SIGN_CODES
                and re.search(r"\d", amount_value)
            ):
                matches += 1
        return matches >= max(1, min(3, len(rows)))

    def _rows_match_bancaribe_layout(self, rows):
        matches = 0
        for row in rows:
            if len(row) < 5:
                continue
            date_value = (row[0] or "").strip()
            sign_value = (row[3] or "").strip().upper()
            if self._detect_date_format(date_value) and sign_value in {"D", "C"}:
                matches += 1
        return matches >= max(1, min(3, len(rows)))

    def _get_column_index(self, columns, column_name):
        if column_name is None or column_name is False:
            return None
        if column_name in columns:
            return columns.index(column_name)
        column_name = str(column_name)
        if column_name in columns:
            return columns.index(column_name)
        if column_name.isdigit():
            return int(column_name)
        return None

    def _detect_number_and_date(self, columns, rows, mapped_columns):
        date_format = "%d/%m/%Y"
        thousands = "dot"
        decimals = "comma"
        date_idx = self._get_column_index(
            columns, mapped_columns.get("cfg_timestamp_column")
        )
        amount_idx = self._get_column_index(
            columns,
            mapped_columns.get("cfg_amount_column")
            or mapped_columns.get("cfg_amount_debit_column"),
        )
        if date_idx is not None:
            for row in rows:
                if date_idx < len(row) and row[date_idx]:
                    detected = self._detect_date_format(row[date_idx])
                    if detected:
                        date_format = detected
                        break
        if amount_idx is not None:
            for row in rows:
                if amount_idx < len(row) and row[amount_idx]:
                    thousands, decimals = self._detect_float_separators(row[amount_idx])
                    break
        return date_format, thousands, decimals

    def _detect_date_format(self, value):
        value = str(value).strip()
        for date_format in DATE_FORMAT_CANDIDATES:
            try:
                datetime.strptime(value, date_format)
                return date_format
            except ValueError:
                continue
        return False

    def _detect_float_separators(self, value):
        value = str(value).strip()
        if re.search(r"-?\d+\.\d{3},\d+", value):
            return "dot", "comma"
        if re.search(r"-?\d+,\d{3}\.\d+", value):
            return "comma", "dot"
        if "," in value and "." not in value:
            return "none", "comma"
        if "." in value and "," not in value:
            parts = value.split(".")
            if len(parts[-1]) == 3 and len(parts) > 1:
                return "dot", "none"
            return "none", "dot"
        return "dot", "comma"

    def _build_temp_mapping(self):
        vals = self._cfg_to_mapping_vals()
        return self.env["account.statement.import.sheet.mapping"].new(vals)

    def _refresh_preview_data(self):
        self.ensure_one()
        if not self.statement_file:
            return
        data_file = self._get_file_data()
        Parser = self.env["account.statement.import.sheet.parser"]
        raw = Parser.get_raw_preview(
            data_file,
            delimiter=self.cfg_delimiter or "comma",
            file_encoding=self.cfg_file_encoding or "utf-8",
            quotechar=self.cfg_quotechar or '"',
            header_lines_skip_count=self.cfg_header_lines_skip_count or 0,
            no_header=bool(self.cfg_no_header),
            offset_column=self.cfg_offset_column or 0,
            limit=20,
        )
        column_mapping = {
            "timestamp_column": self.cfg_timestamp_column or "",
            "amount_column": self.cfg_amount_column or "",
            "amount_debit_column": self.cfg_amount_debit_column or "",
            "amount_credit_column": self.cfg_amount_credit_column or "",
            "debit_credit_column": self.cfg_debit_credit_column or "",
            "balance_column": self.cfg_balance_column or "",
            "description_column": self.cfg_description_column or "",
            "reference_column": self.cfg_reference_column or "",
            "notes_column": self.cfg_notes_column or "",
            "partner_name_column": self.cfg_partner_name_column or "",
            "transaction_id_column": self.cfg_transaction_id_column or "",
            "currency_column": self.cfg_currency_column or "",
            "bank_account_column": self.cfg_bank_account_column or "",
            "bank_name_column": self.cfg_bank_name_column or "",
        }
        parsed = {"lines": [], "error": False, "line_count": 0}
        if self.cfg_timestamp_column and (
            self.cfg_amount_column
            or (self.cfg_amount_debit_column and self.cfg_amount_credit_column)
            or self.cfg_debit_credit_column
        ):
            mapping = self._build_temp_mapping()
            parsed = Parser.get_parsed_preview(
                data_file,
                mapping,
                self.statement_filename or "statement.txt",
                limit=20,
            )
        essential_targets, optional_targets = self._get_preview_targets()
        missing = self._get_missing_required_columns()
        line_count = parsed.get("line_count") or 0
        duplicate_count = parsed.get("duplicate_count") or 0
        new_count = parsed.get("new_count")
        if new_count is None:
            new_count = max(line_count - duplicate_count, 0)
        error = parsed.get("error") or False
        total_rows = raw.get("total_rows") or 0
        state = self._get_preview_state(
            error, missing, line_count, total_rows, new_count, duplicate_count
        )
        message, help_message = self._get_preview_messages(
            state,
            error,
            missing,
            line_count,
            total_rows,
            new_count,
            duplicate_count,
        )
        self.preview_json = {
            "columns": raw.get("columns") or [],
            "rows": raw.get("rows") or [],
            "total_rows": total_rows,
            "is_xlsx": bool(raw.get("is_xlsx")),
            "column_mapping": column_mapping,
            "parsed_lines": parsed.get("lines") or [],
            "essential_targets": essential_targets,
            "optional_targets": optional_targets,
            "targets": essential_targets + optional_targets,
            "state": state,
            "missing": missing,
            "filename": self.statement_filename or "",
            "summary": {
                "title": message,
                "help": help_message,
                "line_count": line_count,
                "total_rows": total_rows,
                "duplicate_count": duplicate_count,
                "new_count": new_count,
            },
        }
        self.preview_line_count = line_count
        self.preview_error = error or False
        self.preview_state = state
        self.preview_message = message
        self.preview_help = help_message

    def _get_preview_targets(self):
        amount_type = self.cfg_amount_type or "simple_value"
        essential = [
            {
                "name": "timestamp_column",
                "label": self.env._("Fecha"),
                "help": self.env._("¿Cuál columna tiene la fecha del movimiento?"),
                "required": True,
            },
        ]
        if amount_type == "distinct_credit_debit":
            essential.extend(
                [
                    {
                        "name": "amount_debit_column",
                        "label": self.env._("Débito"),
                        "help": self.env._("Columna con el dinero que sale."),
                        "required": True,
                    },
                    {
                        "name": "amount_credit_column",
                        "label": self.env._("Crédito"),
                        "help": self.env._("Columna con el dinero que entra."),
                        "required": True,
                    },
                ]
            )
        elif amount_type == "absolute_value":
            essential.extend(
                [
                    {
                        "name": "amount_column",
                        "label": self.env._("Monto"),
                        "help": self.env._("Columna con el valor del monto."),
                        "required": True,
                    },
                    {
                        "name": "debit_credit_column",
                        "label": self.env._("Débito / Crédito"),
                        "help": self.env._(
                            "Columna que indica si el monto es débito o crédito."
                        ),
                        "required": True,
                    },
                ]
            )
        else:
            essential.append(
                {
                    "name": "amount_column",
                    "label": self.env._("Monto"),
                    "help": self.env._(
                        "¿Cuál columna tiene el monto? Si es negativo, suele ser salida."
                    ),
                    "required": True,
                }
            )
        essential.extend(
            [
                {
                    "name": "description_column",
                    "label": self.env._("Descripción"),
                    "help": self.env._("Texto que explica el movimiento."),
                    "required": False,
                },
                {
                    "name": "reference_column",
                    "label": self.env._("Referencia"),
                    "help": self.env._("Referencia bancaria o número de operación."),
                    "required": False,
                },
            ]
        )
        optional = [
            {
                "name": "balance_column",
                "label": self.env._("Saldo"),
                "help": self.env._(
                    "Saldo de la cuenta después de cada línea (opcional)."
                ),
                "required": False,
            },
            {
                "name": "notes_column",
                "label": self.env._("Notas"),
                "help": self.env._("Notas adicionales (opcional)."),
                "required": False,
            },
            {
                "name": "partner_name_column",
                "label": self.env._("Contacto"),
                "help": self.env._("Quién envió o recibió el dinero (opcional)."),
                "required": False,
            },
            {
                "name": "transaction_id_column",
                "label": self.env._("ID único"),
                "help": self.env._("Ayuda a no importar la misma línea dos veces."),
                "required": False,
            },
            {
                "name": "currency_column",
                "label": self.env._("Moneda"),
                "help": self.env._("Solo si el archivo trae una columna de moneda."),
                "required": False,
            },
            {
                "name": "bank_account_column",
                "label": self.env._("Cuenta bancaria"),
                "help": self.env._("Cuenta de la contraparte (opcional)."),
                "required": False,
            },
            {
                "name": "bank_name_column",
                "label": self.env._("Banco"),
                "help": self.env._("Nombre del banco de la contraparte (opcional)."),
                "required": False,
            },
        ]
        if amount_type != "absolute_value":
            optional = [
                target for target in optional if target["name"] != "debit_credit_column"
            ]
        return essential, optional

    def _get_missing_required_columns(self):
        missing = []
        if not self.cfg_timestamp_column:
            missing.append(self.env._("Fecha"))
        amount_type = self.cfg_amount_type or "simple_value"
        if amount_type == "simple_value" and not self.cfg_amount_column:
            missing.append(self.env._("Monto"))
        elif amount_type == "absolute_value" and (
            not self.cfg_amount_column or not self.cfg_debit_credit_column
        ):
            if not self.cfg_amount_column:
                missing.append(self.env._("Monto"))
            if not self.cfg_debit_credit_column:
                missing.append(self.env._("Débito / Crédito"))
        elif amount_type == "distinct_credit_debit" and (
            not self.cfg_amount_debit_column or not self.cfg_amount_credit_column
        ):
            if not self.cfg_amount_debit_column:
                missing.append(self.env._("Débito"))
            if not self.cfg_amount_credit_column:
                missing.append(self.env._("Crédito"))
        return missing

    def _get_preview_state(
        self,
        error,
        missing,
        line_count,
        total_rows,
        new_count=0,
        duplicate_count=0,
    ):
        if error:
            return "error"
        if missing:
            return "warning"
        if line_count > 0 and new_count == 0 and duplicate_count > 0:
            return "warning"
        if new_count > 0:
            return "ready"
        if line_count > 0:
            return "ready"
        if total_rows > 0:
            return "warning"
        return "warning"

    def _get_preview_messages(
        self,
        state,
        error,
        missing,
        line_count,
        total_rows,
        new_count=0,
        duplicate_count=0,
    ):
        if state == "error":
            return (
                self.env._("No pudimos leer el archivo con la configuración actual."),
                self.env._(
                    "Abra opciones avanzadas o cambie el mapeo de columnas e intente de nuevo."
                )
                if not error
                else self.env._("Detalle: %s", error),
            )
        if missing:
            return (
                self.env._("Casi listo: elija las columnas obligatorias."),
                self.env._("Todavía falta: %s", ", ".join(missing)),
            )
        if line_count > 0 and new_count == 0 and duplicate_count > 0:
            return (
                self.env._(
                    "Todos los movimientos ya existen por referencia (%(count)s).",
                    count=duplicate_count,
                ),
                self.env._(
                    "No se importará nada. Esas referencias ya están en este diario."
                ),
            )
        if line_count > 0:
            if duplicate_count:
                return (
                    self.env._(
                        "Listo: %(new)s nuevos, %(dup)s omitidos por referencia repetida.",
                        new=new_count,
                        dup=duplicate_count,
                    ),
                    self.env._(
                        "Los marcados como omitidos ya existen en el diario y no se volverán a importar."
                    ),
                )
            return (
                self.env._(
                    "Listo para importar %(count)s movimientos.",
                    count=line_count,
                ),
                self.env._(
                    "Revise unas líneas abajo. Si se ven bien, pulse Importar extracto."
                ),
            )
        if total_rows > 0:
            return (
                self.env._("Se leyó el archivo, pero no se preparó ningún movimiento."),
                self.env._(
                    "Revise las columnas de fecha/monto o abra opciones avanzadas."
                ),
            )
        return (
            self.env._("No se encontraron filas de datos en este archivo."),
            self.env._("Confirme que subió el estado de cuenta del banco."),
        )
