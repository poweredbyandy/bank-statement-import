# Copyright 2026 andyengit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Bank Statement Sheet Import Preview",
    "summary": "Preview TXT/CSV/XLSX statements and configure reusable sheet mappings",
    "version": "18.0.1.0.5",
    "category": "Accounting",
    "website": "https://github.com/OCA/bank-statement-import",
    "author": "andyengit, Odoo Community Association (OCA)",
    "maintainers": ["andyengit"],
    "license": "AGPL-3",
    "installable": True,
    "depends": [
        "account_statement_import_sheet_file",
    ],
    "external_dependencies": {
        "python": ["openpyxl", "chardet"],
    },
    "data": [
        "security/ir.model.access.csv",
        "views/account_journal_views.xml",
        "views/account_statement_import_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_statement_import_sheet_preview/static/src/statement_import_preview/statement_import_preview.scss",
            "account_statement_import_sheet_preview/static/src/statement_import_preview/statement_import_preview.xml",
            "account_statement_import_sheet_preview/static/src/statement_import_preview/statement_import_preview.esm.js",
        ],
    },
}
