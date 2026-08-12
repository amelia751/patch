import { Sidebar } from "@/components/layout/sidebar";
import { Toaster } from "@/components/ui/sonner";

/**
 * The application chrome: a fixed rail on the left, a scrolling page beside it.
 *
 * A server component — there is no client-side global state to provide. Theme
 * lives on the `<html>` class, and every page reads the control plane on the
 * server.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div className="flex h-dvh overflow-hidden bg-background text-foreground">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">{children}</div>
      </div>
      <Toaster position="bottom-right" />
    </>
  );
}
