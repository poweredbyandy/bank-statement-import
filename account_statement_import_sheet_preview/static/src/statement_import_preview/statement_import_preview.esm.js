/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useState } from "@odoo/owl";

export class StatementImportPreviewField extends Component {
    static template = "account_statement_import_sheet_preview.StatementImportPreview";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.state = useState({
            showOptional: false,
            showRawFile: false,
        });
    }

    get preview() {
        return this.props.record.data[this.props.name] || {};
    }

    get columns() {
        return this.preview.columns || [];
    }

    get rows() {
        return this.preview.rows || [];
    }

    get parsedLines() {
        return this.preview.parsed_lines || [];
    }

    get essentialTargets() {
        return this.preview.essential_targets || this.preview.targets || [];
    }

    get optionalTargets() {
        return this.preview.optional_targets || [];
    }

    get columnMapping() {
        return this.preview.column_mapping || {};
    }

    get summary() {
        return this.preview.summary || {};
    }

    get duplicateCount() {
        return this.summary.duplicate_count || 0;
    }

    get newCount() {
        return this.summary.new_count || 0;
    }

    get previewState() {
        return this.preview.state || "warning";
    }

    get hasPreview() {
        return Boolean(this.columns.length || this.rows.length);
    }

    get statusClass() {
        return {
            ready: "alert-success",
            warning: "alert-warning",
            error: "alert-danger",
            empty: "alert-secondary",
        }[this.previewState] || "alert-secondary";
    }

    get statusIcon() {
        return {
            ready: "fa-check-circle",
            warning: "fa-exclamation-triangle",
            error: "fa-times-circle",
            empty: "fa-info-circle",
        }[this.previewState] || "fa-info-circle";
    }

    get mappedColumnIndexes() {
        const indexes = {};
        const mapping = this.columnMapping;
        for (const [target, columnName] of Object.entries(mapping)) {
            if (!columnName) {
                continue;
            }
            const index = this.columns.indexOf(columnName);
            if (index >= 0) {
                indexes[index] = target;
            }
        }
        return indexes;
    }

    selectedColumn(targetName) {
        return this.columnMapping[targetName] || "";
    }

    isMissing(target) {
        return Boolean(target.required && !this.selectedColumn(target.name));
    }

    columnBadge(columnIndex) {
        const target = this.mappedColumnIndexes[columnIndex];
        if (!target) {
            return "";
        }
        const allTargets = [...this.essentialTargets, ...this.optionalTargets];
        const match = allTargets.find((item) => item.name === target);
        return match ? match.label : "";
    }

    formatAmount(value) {
        if (value === null || value === undefined || value === "") {
            return "";
        }
        const number = Number(value);
        if (Number.isNaN(number)) {
            return value;
        }
        return number.toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    amountClass(value) {
        const number = Number(value);
        if (Number.isNaN(number) || number === 0) {
            return "";
        }
        return number < 0 ? "text-danger" : "text-success";
    }

    toggleOptional() {
        this.state.showOptional = !this.state.showOptional;
    }

    toggleRawFile() {
        this.state.showRawFile = !this.state.showRawFile;
    }

    async onTargetChange(targetName, event) {
        const value = event.target.value || false;
        const cfgField = `cfg_${targetName}`;
        const preview = { ...this.preview };
        preview.column_mapping = {
            ...this.columnMapping,
            [targetName]: value || "",
        };
        await this.props.record.update({
            [cfgField]: value,
            [this.props.name]: preview,
        });
    }
}

export const statementImportPreviewField = {
    component: StatementImportPreviewField,
    displayName: _t("Statement Import Preview"),
    supportedTypes: ["json", "jsonb"],
};

registry.category("fields").add("statement_import_preview", statementImportPreviewField);
