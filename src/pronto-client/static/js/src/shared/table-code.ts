/**
 * Helpers to build and validate table codes.
 *
 * Format: <AREA>-MNN
 *  - AREA: 1-3 alphanumeric chars (uppercase), no spaces
 *  - NN: table number 01-99 (two digits)
 *  - Full regex: ^[A-Z0-9]{1,3}-M(0[1-9]|[1-9][0-9])$
 */
export const TABLE_CODE_REGEX = /^[A-Z0-9]{1,3}-M(0[1-9]|[1-9][0-9])$/;

export type ParsedTableCode = {
    areaCode: string;
    tableNumber: number;
    code: string;
};

export function normalizeAreaCode(areaCode: string): string {
    const cleaned = (areaCode || '').trim().replace(/[^A-Za-z0-9]/g, '').toUpperCase();
    return cleaned.slice(0, 3);
}

export function buildTableCode(areaCode: string, tableNumber: number): string {
    const normalizedArea = normalizeAreaCode(areaCode);
    if (!normalizedArea) {
        throw new Error('El código de área de la mesa es obligatorio (1 a 3 caracteres alfanuméricos).');
    }
    if (normalizedArea.length > 3) {
        throw new Error('El código de área de la mesa no puede tener más de 3 caracteres.');
    }

    if (!Number.isInteger(tableNumber) || tableNumber < 1 || tableNumber > 99) {
        throw new Error('El número de mesa debe ser un entero entre 1 y 99.');
    }

    const code = `${normalizedArea}-M${String(tableNumber).padStart(2, '0')}`;
    if (!TABLE_CODE_REGEX.test(code)) {
        throw new Error('El código de mesa no cumple con el formato esperado (AREA-MNN).');
    }
    return code;
}

export function validateTableCode(code: string, raiseError = false): boolean {
    const normalized = (code || '').trim().toUpperCase();
    const isValid = TABLE_CODE_REGEX.test(normalized);
    if (!isValid && raiseError) {
        throw new Error('Código de mesa inválido. Usa el formato AREA-MNN (ej. B-M01).');
    }
    return isValid;
}

export function parseTableCode(code: string): ParsedTableCode | null {
    const normalized = (code || '').trim().toUpperCase();
    const match = normalized.match(TABLE_CODE_REGEX);
    if (!match) return null;
    const areaCode = match[0].split('-')[0];
    const tableNumber = Number(match[1]);
    return { areaCode, tableNumber, code: normalized };
}

export function deriveAreaCodeFromLabel(label?: string | null, fallback = 'G'): string {
    const cleanedLabel = (label || '').trim();
    if (!cleanedLabel) return normalizeAreaCode(fallback) || 'G';
    const normalized = cleanedLabel.toLowerCase();
    if (normalized.startsWith('vip')) return 'V';
    if (normalized.startsWith('barra') || normalized.startsWith('bar')) return 'B';
    if (normalized.startsWith('mesa')) return 'M';
    return normalizeAreaCode(cleanedLabel) || normalizeAreaCode(fallback) || 'G';
}
