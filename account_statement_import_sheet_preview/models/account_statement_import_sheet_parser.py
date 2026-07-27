# Copyright 2026 andyengit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from csv import reader
from io import BytesIO, StringIO
from zipfile import BadZipFile

from odoo import api, models

_logger = logging.getLogger(__name__)

try:
    import chardet
    import openpyxl
except (OSError, ImportError) as err:  # pragma: no cover
    _logger.debug(err)


class AccountStatementImportSheetParser(models.TransientModel):
    _inherit = "account.statement.import.sheet.parser"

    @api.model
    def get_raw_preview(
        self,
        data_file,
        delimiter="comma",
        file_encoding="utf-8",
        quotechar='"',
        header_lines_skip_count=0,
        no_header=False,
        offset_column=0,
        limit=20,
    ):
        """Return raw columns/rows for UI preview without requiring a full mapping."""
        Mapping = self.env["account.statement.import.sheet.mapping"]
        delimiter_char = Mapping._decode_column_delimiter_character(delimiter)
        is_xlsx = False
        rows = []
        try:
            workbook = openpyxl.load_workbook(
                filename=BytesIO(data_file),
                data_only=True,
                read_only=True,
            )
            sheet = workbook.worksheets[0]
            is_xlsx = True
            for row in sheet.iter_rows(values_only=True):
                rows.append(["" if cell is None else str(cell).strip() for cell in row])
            workbook.close()
        except (BadZipFile, Exception):
            try:
                decoded = data_file.decode(file_encoding or "utf-8")
            except UnicodeDecodeError:
                detected = chardet.detect(data_file).get("encoding") or "utf-8"
                decoded = data_file.decode(detected, errors="replace")
                file_encoding = detected
            csv_options = {}
            if delimiter_char:
                csv_options["delimiter"] = delimiter_char
            if quotechar:
                csv_options["quotechar"] = quotechar
            rows = [
                [str(value).strip() if value is not None else "" for value in row]
                for row in reader(StringIO(decoded), **csv_options)
            ]

        if offset_column:
            rows = [row[offset_column:] for row in rows]

        header_skip = max(header_lines_skip_count - 1, 0) if not no_header else 0
        if no_header:
            max_len = max((len(row) for row in rows), default=0)
            columns = [str(index) for index in range(max_len)]
            data_rows = rows
        else:
            if len(rows) <= header_skip:
                return {
                    "columns": [],
                    "rows": [],
                    "is_xlsx": is_xlsx,
                    "file_encoding": file_encoding,
                }
            header = rows[header_skip]
            columns = [
                value if value else f"Column {index}"
                for index, value in enumerate(header)
            ]
            data_rows = rows[header_skip + 1 :]

        data_rows = [row for row in data_rows if any(row)]
        return {
            "columns": columns,
            "rows": data_rows[:limit],
            "total_rows": len(data_rows),
            "is_xlsx": is_xlsx,
            "file_encoding": file_encoding,
        }

    @api.model
    def get_parsed_preview(self, data_file, mapping, filename, limit=20):
        """Dry-run parse using the standard sheet parser."""
        journal = self.env["account.journal"].browse(self.env.context.get("journal_id"))
        currency_code = (journal.currency_id or journal.company_id.currency_id).name
        try:
            lines = self._parse_lines(mapping, data_file, currency_code)
        except Exception as exc:
            return {
                "lines": [],
                "error": str(exc),
                "line_count": 0,
                "duplicate_count": 0,
                "new_count": 0,
            }
        Line = self.env["account.bank.statement.line"]
        existing_refs = Line._sheet_preview_existing_refs(journal)
        preview_lines = []
        duplicate_count = 0
        for line in lines:
            ref = Line._sheet_preview_normalize_ref(line.get("reference"))
            is_duplicate = bool(
                Line._sheet_preview_is_reliable_ref(ref) and ref in existing_refs
            )
            if is_duplicate:
                duplicate_count += 1
            preview_lines.append(
                {
                    "date": line["timestamp"].strftime("%Y-%m-%d")
                    if line.get("timestamp")
                    else "",
                    "amount": float(line.get("amount") or 0.0),
                    "balance": float(line["balance"])
                    if line.get("balance") is not None
                    else None,
                    "payment_ref": line.get("description") or "",
                    "ref": ref,
                    "is_duplicate": is_duplicate,
                    "duplicate_note": self.env._("Se omitirá: referencia ya importada")
                    if is_duplicate
                    else "",
                }
            )
        return {
            "lines": preview_lines[:limit],
            "error": False,
            "line_count": len(lines),
            "duplicate_count": duplicate_count,
            "new_count": len(lines) - duplicate_count,
        }
