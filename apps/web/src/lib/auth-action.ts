/** Read Firebase / Identity Platform action params from a landing URL. */

export function parseAuthAction(
  search: URLSearchParams,
  hash = "",
): { mode: string; oobCode: string } {
  const rawHash = hash.startsWith("#") ? hash.slice(1) : hash;
  const fromHash = new URLSearchParams(rawHash);
  const pick = (...keys: string[]) => {
    for (const key of keys) {
      const value = search.get(key) || fromHash.get(key);
      if (value) return value;
    }
    return "";
  };

  let mode = pick("mode");
  let oobCode = pick("oobCode", "oob_code");

  const nested = search.get("link") || search.get("continueUrl") || fromHash.get("continueUrl") || "";
  if (nested && (!mode || !oobCode)) {
    try {
      const url = new URL(nested);
      mode = mode || url.searchParams.get("mode") || "";
      oobCode = oobCode || url.searchParams.get("oobCode") || url.searchParams.get("oob_code") || "";
    } catch {
      // The nested value was not a URL; ignore it.
    }
  }

  return { mode, oobCode };
}
