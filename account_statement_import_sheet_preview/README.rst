=====================================
Bank Statement Sheet Import Preview
=====================================

.. 
   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
   !! This file is generated from readme/ fragments. !!
   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

.. |badge1| image:: https://img.shields.io/badge/maturity-Beta-yellow.png
    :target: https://odoo-community.org/page/development-status
    :alt: Beta
.. |badge2| image:: https://img.shields.io/badge/licence-AGPL--3-blue.png
    :target: http://www.gnu.org/licenses/agpl-3.0-standalone.html
    :alt: License: AGPL-3
.. |badge3| image:: https://img.shields.io/badge/github-OCA%2Fbank--statement--import-lightgray.png?logo=github
    :target: https://github.com/OCA/bank-statement-import/tree/18.0/account_statement_import_sheet_preview
    :alt: OCA/bank-statement-import

|badge1| |badge2| |badge3|

This module improves TXT/CSV/XLSX bank statement import by adding a live
preview and guided mapping configuration inside the import wizard.

Instead of maintaining dozens of static mappings for small format differences
(delimiter, encoding, date format, column names), users can:

* upload a statement file
* preview detected columns and rows
* map columns visually
* auto-save the mapping
* reuse journal-specific mappings, with the last used one as default

**Table of contents**

.. contents::
   :local:

Configuration
=============

On each bank journal (Accounting → Configuration → Journals):

1. Open the journal form.
2. In **Advanced Settings**, find **Statement Import Map**.
3. Add one or more sheet mappings in **Statement Sheet Mappings**.
4. **Last used mapping** is updated automatically after each successful import.

If a journal has mappings configured, the import wizard only offers those
mappings. If none are configured, all mappings remain available and new ones
can be auto-saved from the wizard.

Usage
=====

1. Open a bank journal and start the statement import wizard.
2. Upload a TXT, CSV or XLSX file.
3. The wizard auto-detects delimiter, encoding, date format and common column
   names (Fecha, Monto, Referencia, Descripción, Balance, etc.).
4. Review the preview table and parsed lines.
5. Adjust format options or column mapping if needed.
6. Optionally click **Save Mapping** to store/link the mapping immediately.
7. Click **Import and View**.

With **Auto-save mapping** enabled (default), the mapping is created or updated
and set as the journal last-used mapping on import.

Bug Tracker
===========

Bugs are tracked on `GitHub Issues <https://github.com/OCA/bank-statement-import/issues>`_.
In case of trouble, please check there if your issue has already been reported.

Credits
=======

Authors
-------

* andyengit

Contributors
------------

* andyengit <https://github.com/andyengit>

Maintainers
-----------

This module is maintained by the OCA.

.. image:: https://odoo-community.org/logo.png
   :alt: Odoo Community Association
   :target: https://odoo-community.org

OCA, or the Odoo Community Association, is a nonprofit organization whose
mission is to support the collaborative development of Odoo features and
promote its widespread use.

Current maintainer:

* andyengit

This module is part of the `OCA/bank-statement-import <https://github.com/OCA/bank-statement-import/tree/18.0/account_statement_import_sheet_preview>`_ project on GitHub.
