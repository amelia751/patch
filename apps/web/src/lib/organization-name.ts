function nameToken(raw: string | null | undefined): string | null {
  const token = (raw ?? "").trim().split(/\s+/)[0] ?? "";
  if (!token) {
    return null;
  }
  return token[0].toUpperCase() + token.slice(1);
}

export function firstNameFromUser(displayName: string | null | undefined): string {
  const fromDisplay = nameToken(displayName);
  if (!fromDisplay) {
    throw new Error("first name is required");
  }
  return fromDisplay;
}

export function organizationNameFromUser(
  displayName: string | null | undefined,
): { name: string; slug: string } {
  const name = `${firstNameFromUser(displayName)}'s Organization`;
  const slug =
    name
      .toLowerCase()
      .replace(/'/g, "")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "") || "organization";
  return { name, slug };
}
