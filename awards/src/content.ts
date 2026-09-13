/**
 * Text that appears on the site itself, kept out of the Worker entry module.
 *
 * The entry module's named exports are handlers as far as the runtime is concerned -
 * exporting a string from it fails at startup with "Incorrect type for map entry: the
 * provided value is not of type 'function or ExportedHandler'". Shared copy lives here.
 */

/** On every rendered page and in every JSON payload. There is no flag that removes it. */
export const DISCLOSURE =
  "This is informational only, derived from public data on the dates shown. It is not an " +
  "eligibility determination, and not legal, tax, or accounting advice. Verify against the " +
  "official source before relying on it.";
