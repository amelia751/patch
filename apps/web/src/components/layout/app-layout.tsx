"use client";

import { useCallback, createContext, useContext } from "react";
import { usePathname } from "next/navigation";
import { Header } from "@/components/interface/shared/header";
import Sidebar from "@/components/interface/shared/sidebar";
import { useAuth } from "@/lib/auth-context";
import { RootAuthGate } from "@/components/interface/auth/root-auth-gate";
import { Spinner } from "@/components/ui/spinner";

interface AppLayoutProps {
  children: React.ReactNode;
}

// =============================================================================
// Console Panel Context - for controlling console from anywhere in the app
// =============================================================================
interface ConsolePanelContextType {
  openConsole: () => void;
  focusThread: (threadId: string) => void;
  activeThreadId: string | null;
}

const ConsolePanelContext = createContext<ConsolePanelContextType>({
  openConsole: () => {},
  focusThread: () => {},
  activeThreadId: null,
});

export function useConsolePanel() {
  return useContext(ConsolePanelContext);
}

export function AppLayout({ children }: AppLayoutProps) {
  const pathname = usePathname();
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const isStandalonePage = pathname === "/hub";

  // Threads are hidden. Runs owns the live agent log. Keep the context
  // so existing callers (notifications, workspace) do not break.
  const consolePanelValue = {
    openConsole: () => {},
    focusThread: () => {},
    activeThreadId: null as string | null,
  };

  const handleSidebarWidthChange = useCallback((_width: number) => {}, []);

  if (isStandalonePage) {
    return <>{children}</>;
  }

  if (pathname === "/" && authLoading) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-[#0a0a0a]">
        <Spinner className="h-4 w-4 text-[var(--text-secondary)]" />
      </div>
    );
  }

  if (pathname === "/" && !isAuthenticated) {
    return (
      <>
        <RootAuthGate />
        {children}
      </>
    );
  }

  return (
    <ConsolePanelContext.Provider value={consolePanelValue}>
      <div className="h-screen w-screen overflow-hidden bg-[var(--bg-secondary)] transition-colors">
        <div className="flex h-full">
          <Sidebar onWidthChange={handleSidebarWidthChange} />

          <div className="flex flex-col flex-1 min-w-0 h-full">
            <Header />
            <div className="flex flex-1 h-full relative min-h-0 overflow-hidden">
              <div className="flex-1 min-w-0 relative h-full bg-[var(--bg-secondary)] overflow-hidden transition-colors">
                <div className="h-full flex flex-col min-w-0">
                  {children}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </ConsolePanelContext.Provider>
  );
}
