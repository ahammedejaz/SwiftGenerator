/**
 * Identifier checks for live feedback while typing.
 *
 * This is deliberately a mirror of `app/domain/identifiers.py`, not a second authority.
 * The server validates every value again and is the only thing that decides whether a
 * message is valid; everything here exists so a tester learns about a mistyped check digit
 * at the twelfth character rather than after pressing Generate.
 *
 * Deterministic arithmetic. No model call, here or anywhere near a field.
 */

/** The field's own literal, stripped on paste so it can never end up in the value twice. */
const LEADING_ISIN = /^ISIN[\s:]+/i;

const ISIN_LENGTH = 12;
const ISIN_SHAPE = /^[A-Z]{2}[A-Z0-9]{9}[0-9]$/;
const BIC_SHAPE = /^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$/;

export interface IsinVerdict {
  formatValid: boolean;
  checkDigitValid: boolean;
  expectedCheckDigit: string | null;
  /** What to say while the value is still incomplete. */
  hint: string | null;
}

/**
 * Uppercase, drop spacing, and remove the field's literal if it was pasted in.
 *
 * Only presentation is touched. The identifier's own characters are never rewritten —
 * silently repairing a check digit would hide the mistake the tester needs to see.
 */
export function normaliseIsin(raw: string): string {
  return raw
    .toUpperCase()
    .replace(LEADING_ISIN, "")
    .replace(/[^A-Z0-9]/g, "");
}

/** The ISO 6166 modulus-10 check digit for the first eleven characters. */
export function isinCheckDigit(body: string): string | null {
  if (body.length !== ISIN_LENGTH - 1) return null;
  let expanded = "";
  for (const character of body.toUpperCase()) {
    if (character >= "A" && character <= "Z") {
      expanded += String(character.charCodeAt(0) - 55);
    } else if (character >= "0" && character <= "9") {
      expanded += character;
    } else {
      return null;
    }
  }
  let total = 0;
  for (let index = 0; index < expanded.length; index += 1) {
    // Double every second digit counting from the right.
    const fromRight = expanded.length - 1 - index;
    let digit = Number(expanded[index]);
    if (fromRight % 2 === 0) {
      digit *= 2;
      if (digit > 9) digit -= 9;
    }
    total += digit;
  }
  return String((10 - (total % 10)) % 10);
}

export function checkIsin(value: string): IsinVerdict {
  const candidate = value.trim().toUpperCase();
  const expected = isinCheckDigit(candidate.slice(0, ISIN_LENGTH - 1));

  if (candidate.length !== ISIN_LENGTH) {
    return {
      formatValid: false,
      checkDigitValid: false,
      expectedCheckDigit: expected,
      hint: candidate.length > 0 && !/^[A-Z]{0,2}/.test(candidate) ? "Starts with two letters" : null,
    };
  }
  if (!/^[A-Z]{2}/.test(candidate)) {
    return {
      formatValid: false,
      checkDigitValid: false,
      expectedCheckDigit: expected,
      hint: "The first two characters must be letters",
    };
  }
  if (!/[0-9]$/.test(candidate)) {
    return {
      formatValid: false,
      checkDigitValid: false,
      expectedCheckDigit: expected,
      hint: "The last character must be a numeric check digit",
    };
  }
  if (!ISIN_SHAPE.test(candidate)) {
    return {
      formatValid: false,
      checkDigitValid: false,
      expectedCheckDigit: expected,
      hint: "Letters and digits only",
    };
  }
  return {
    formatValid: true,
    checkDigitValid: expected === candidate[ISIN_LENGTH - 1],
    expectedCheckDigit: expected,
    hint: null,
  };
}

/**
 * Whether the value has a BIC's shape.
 *
 * Says nothing about whether the BIC is registered — no directory is integrated, so no
 * part of this application may claim one.
 */
export function isBicShaped(value: string): boolean {
  return BIC_SHAPE.test(value.trim().toUpperCase());
}
