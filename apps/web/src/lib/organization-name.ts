export const FALLBACK_ORGANIZATION_NAME = "First Organization";

const NAME_TOKEN = /^[A-Za-z][A-Za-z'-]*$/;

function nameToken(raw: string | null | undefined): string | null {
  const token = (raw ?? "").trim().split(/\s+/)[0] ?? "";
  if (!NAME_TOKEN.test(token)) {
    return null;
  }
  return token[0].toUpperCase() + token.slice(1);
}

export function firstNameFromUser(
  displayName: string | null | undefined,
  email: string | null | undefined,
): string | null {
  const fromDisplay = nameToken(displayName);
  if (fromDisplay) {
    return fromDisplay;
  }
  const local = (email ?? "").split("@", 1)[0]?.trim() ?? "";
  if (local && !local.includes(".") && !local.includes("+")) {
    return nameToken(local);
  }
  return null;
}

export function organizationNameFromUser(
  displayName: string | null | undefined,
  email: string | null | undefined,
): { name: string; slug: string } {
  const first = firstNameFromUser(displayName, email);
  const name = first ? `${first}'s Organization` : FALLBACK_ORGANIZATION_NAME;
  const slug =
    name
      .toLowerCase()
      .replace(/'/g, "")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "") || "first-organization";
  return { name, slug };
}
