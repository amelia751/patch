import { Header } from "@/components/layout/header";
import { ControlPlaneStatus } from "@/components/patch/control-plane-status";

/** Header plus a scrolling content column — the frame every page uses. */
export function Page({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <>
      <Header
        title={title}
        description={description}
        status={<ControlPlaneStatus />}
        actions={actions}
      />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-7xl space-y-6 px-6 py-6">{children}</div>
      </main>
    </>
  );
}

/** A titled section with an optional right-aligned note. */
export function Section({
  title,
  note,
  children,
}: {
  title: string;
  note?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          {title}
        </h2>
        {note ? <div className="text-xs text-muted-foreground">{note}</div> : null}
      </div>
      {children}
    </section>
  );
}
