/** Workspace folder scope for secrets. `/` is a workspace's repo root, not a project-wide bucket. */

export type SecretWorkspaceRef = {
  id: string;
  workspace_path?: string | null;
};

export function normalizeRepoPath(path: string | null | undefined): string {
  if (path == null || !String(path).trim()) return "";
  return String(path).replace(/^\/+/u, "").replace(/\/+$/u, "");
}

/** Prefer the whole-repo workspace (empty path), else the first workspace. */
export function rootWorkspaceId(workspaces: SecretWorkspaceRef[]): string | null {
  if (workspaces.length === 0) return null;
  const atRoot = workspaces.find((w) => !normalizeRepoPath(w.workspace_path));
  return (atRoot ?? workspaces[0]).id;
}

/**
 * Folder you are in → workspace id.
 * Repo root (`/`) binds to that repo's root workspace, never a standalone shared `/`.
 */
export function workspaceIdForSelectedFolder(
  folderSegments: string[],
  workspaces: SecretWorkspaceRef[]
): string | null {
  const here = folderSegments.join("/");
  if (!here) return rootWorkspaceId(workspaces);

  const exact = workspaces.find((w) => normalizeRepoPath(w.workspace_path) === here);
  if (exact) return exact.id;

  let longestRoot: { id: string; n: number } | null = null;
  for (const w of workspaces) {
    const root = normalizeRepoPath(w.workspace_path);
    if (!root) continue;
    const inside = here === root || here.startsWith(`${root}/`);
    if (!inside) continue;
    if (!longestRoot || root.length > longestRoot.n) {
      longestRoot = { id: w.id, n: root.length };
    }
  }
  if (longestRoot) return longestRoot.id;

  return rootWorkspaceId(workspaces);
}
