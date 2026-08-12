"use client";

import { useState, useRef, useEffect, useCallback, createContext, useContext } from "react";
import { usePathname } from "next/navigation";
import { Header } from "@/components/interface/shared/header";
import { Threads } from "@/components/console";
import Sidebar from "@/components/interface/shared/sidebar";
import { useProject } from "@/lib/project-context";
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
  const { currentProject } = useProject();
  const [sidebarWidth, setSidebarWidth] = useState(64);
  const [chatWidth, setChatWidth] = useState(500);
  const [isResizing, setIsResizing] = useState(false);
  const [focusedThreadId, setFocusedThreadId] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Read ?thread= from URL on mount (like Cursor's deep-link to a conversation)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const threadFromUrl = params.get("thread");
    if (threadFromUrl) {
      setFocusedThreadId(threadFromUrl);
    }
  }, []);

  // Standalone pages without app interface
  const isStandalonePage = pathname === "/hub";

  // Console panel controls
  const openConsole = useCallback(() => {
    // Ensure console is visible (could animate or expand if collapsed)
    // For now, just set a minimum width
    if (chatWidth < 400) {
      setChatWidth(500);
    }
  }, [chatWidth]);

  const focusThread = useCallback((threadId: string) => {
    setFocusedThreadId(threadId);
    openConsole();
  }, [openConsole]);

  const consolePanelValue = { openConsole, focusThread, activeThreadId: focusedThreadId };

  const handleSidebarWidthChange = useCallback((width: number) => {
    setSidebarWidth(width);
  }, []);

  const handleChatResizeStart = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing || !containerRef.current) return;

      const containerRect = containerRef.current.getBoundingClientRect();
      const newChatWidth = containerRect.right - e.clientX;

      const minChatWidth = 300;
      const maxChatWidth = containerRect.width * 0.67;

      if (newChatWidth >= minChatWidth && newChatWidth <= maxChatWidth) {
        setChatWidth(newChatWidth);
      }
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    if (isResizing) {
      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    }

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isResizing]);

  // Render standalone pages without app interface
  if (isStandalonePage) {
    return <>{children}</>;
  }

  // While the initial auth check is in flight, show a spinner instead of
  // flashing the sign-in gate or the app shell.
  if (pathname === "/" && authLoading) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-[#0a0a0a]">
        <Spinner className="h-4 w-4 text-[var(--text-secondary)]" />
      </div>
    );
  }

  // Auth resolved and user is not authenticated — show the split sign-in page.
  if (pathname === "/" && !isAuthenticated) {
    return (
      <>
        <RootAuthGate />
        {children}
      </>
    );
  }

  // Convert currentProject to the format Threads expects
  // Thread info (threadId, threadNumber) will be fetched by Threads component via project status API
  const projectForThreads = currentProject ? {
    id: currentProject.id,
    name: currentProject.name,
    status: currentProject.status,
    threadId: currentProject.threadId,  // May be undefined initially, fetched later
    threadNumber: currentProject.threadNumber,  // May be undefined initially, fetched later
  } : null;

  return (
    <ConsolePanelContext.Provider value={consolePanelValue}>
      <div className="h-screen w-screen overflow-hidden bg-[var(--bg-secondary)] transition-colors">
        <div className="flex h-full">
          {/* Sidebar */}
          <Sidebar onWidthChange={handleSidebarWidthChange} />

          {/* Main Content Area */}
          <div className="flex flex-col flex-1 min-w-0 h-full">
            <Header />

            <div
              ref={containerRef}
              className="flex flex-1 h-full relative min-h-0 overflow-hidden"
            >
              {/* Canvas Panel (Left) - Page Content */}
              <div className="flex-1 min-w-0 relative h-full bg-[var(--bg-secondary)] border-r border-[var(--border-color)] overflow-hidden transition-colors">
                <div className="h-full flex flex-col min-w-0">
                  {children}
                </div>
              </div>

              {/* Resize Handle */}
              <div
                className="absolute top-0 h-full w-3 cursor-col-resize group z-50 flex items-center justify-center hover:bg-[var(--bg-tertiary)]/50 transition-colors"
                style={{ right: `${chatWidth}px` }}
                onMouseDown={handleChatResizeStart}
              >
                <div className="w-0.5 h-8 bg-[var(--border-color)] rounded-full group-hover:bg-[var(--text-secondary)] transition-colors" />
              </div>

              {/* Console Panel (Right) */}
              <div
                className="flex-shrink-0 relative h-full bg-[var(--bg-primary)] border-l border-[var(--border-color)] transition-colors"
                style={{ width: `${chatWidth}px` }}
              >
                <Threads 
                  project={projectForThreads}
                  initialThreadId={focusedThreadId}
                  onThreadSelect={setFocusedThreadId}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </ConsolePanelContext.Provider>
  );
}
