import { ThemeToggle } from "@/components/layout/theme-toggle";

/**
 * The page header. `status` is a slot rather than a prop so the server can
 * render live control-plane readiness into it without this component needing
 * to fetch anything itself.
 */
export function Header({
  title,
  description,
  status,
  actions,
}: {
  title: string;
  description?: string;
  status?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <header className="border-b border-border bg-[var(--surface-primary)]">
      <div className="flex flex-wrap items-start justify-between gap-4 px-6 py-5">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="truncate text-xl font-semibold tracking-tight">{title}</h1>
            {status}
          </div>
          {description ? (
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          {actions}
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
