// No provider identifier anywhere in this file: it proves the scanner reports
// files it read without inventing a finding in them.
export function slugify(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, "-");
}
