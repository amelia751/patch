// No provider identifier anywhere in this file: it proves the scanner reports
// files it read without inventing a finding in them.
export function formatAmount(cents: number): string {
  return (cents / 100).toFixed(2);
}
