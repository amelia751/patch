/**
 * Tailwind class fragments that should track the app brand (`--primary` in `app/globals.css`).
 * Use for hooks and config objects; prefer `bg-primary` / `text-primary` directly in JSX when obvious.
 * Success/health/destructive semantics stay on emerald/red/amber palette classes elsewhere.
 */
export const uiTheme = {
  textProgress: "text-primary",
  toolSearch: "text-primary",
  auditCodeGenerate: "text-primary bg-primary/10",
} as const;
