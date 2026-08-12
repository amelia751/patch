"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  GoogleTestConnectDialog,
  type GoogleTestSessionSlice,
} from "@/components/interface/ops/configure-tab/google-test-connect-dialog";
import { TestSignInLearnMoreDialog } from "@/components/interface/ops/configure-tab/test-sign-in-learn-more-dialog";
import { useAuth } from "@/lib/auth-context";
import { useProject } from "@/lib/project-context";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const defaultGoogle: GoogleTestSessionSlice = { status: "disconnected" };

interface TestGoogleSessionContextValue {
  googleSessionIconGeneration: number;
  google: GoogleTestSessionSlice;
  connectDialogOpen: boolean;
  openGoogleTestConnect: () => void;
  setConnectDialogOpen: (open: boolean) => void;
  /** Opens Configure dialog (same as openGoogleTestConnect); chat CTA uses this name. */
  startGoogleTestSignIn: () => void;
  disconnectGoogleTestSession: () => void;
  testSignInLearnMoreOpen: boolean;
  setTestSignInLearnMoreOpen: (open: boolean) => void;
  openTestSignInLearnMore: () => void;
  refreshAppSessionStatus: () => Promise<void>;
}

const TestGoogleSessionContext = createContext<TestGoogleSessionContextValue | null>(null);

export function useTestGoogleSession(): TestGoogleSessionContextValue {
  const ctx = useContext(TestGoogleSessionContext);
  if (!ctx) {
    throw new Error("useTestGoogleSession must be used within TestGoogleSessionProvider");
  }
  return ctx;
}

export function useTestGoogleSessionOptional(): TestGoogleSessionContextValue | null {
  return useContext(TestGoogleSessionContext);
}

function mapStatusToSlice(data: {
  connected?: boolean;
  connected_as?: string | null;
  session_display_name?: string | null;
  auth_exchange_url?: string | null;
  captured_at?: string | null;
}): GoogleTestSessionSlice {
  if (!data.connected) {
    return { status: "disconnected" };
  }
  let capturedAt: string | undefined;
  if (data.captured_at) {
    try {
      capturedAt = new Date(data.captured_at).toLocaleString();
    } catch {
      capturedAt = data.captured_at;
    }
  }
  return {
    status: "connected",
    connectedAs: data.connected_as ?? undefined,
    sessionDisplayName: data.session_display_name ?? undefined,
    authExchangeUrl: data.auth_exchange_url ?? undefined,
    capturedAt,
  };
}

export function TestGoogleSessionProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const { currentProject } = useProject();
  const projectId = currentProject?.id ?? null;

  const [googleSessionIconGeneration, setGoogleSessionIconGeneration] = useState(0);
  const [google, setGoogle] = useState<GoogleTestSessionSlice>(defaultGoogle);
  const [connectDialogOpen, setConnectDialogOpen] = useState(false);
  const [testSignInLearnMoreOpen, setTestSignInLearnMoreOpen] = useState(false);

  const refreshAppSessionStatus = useCallback(async () => {
    if (!isAuthenticated || !projectId) {
      setGoogle(defaultGoogle);
      return;
    }
    try {
      const res = await fetch(`${API_URL}/api/projects/${projectId}/app-session`, {
        credentials: "include",
      });
      if (!res.ok) {
        setGoogle(defaultGoogle);
        return;
      }
      const data = await res.json();
      setGoogle(mapStatusToSlice(data));
    } catch {
      setGoogle(defaultGoogle);
    }
  }, [isAuthenticated, projectId]);

  useEffect(() => {
    void refreshAppSessionStatus();
  }, [refreshAppSessionStatus]);

  const disconnectGoogleTestSession = useCallback(async () => {
    if (projectId && isAuthenticated) {
      try {
        await fetch(`${API_URL}/api/projects/${projectId}/app-session`, {
          method: "DELETE",
          credentials: "include",
        });
      } catch {
        /* still clear local UI */
      }
    }
    setGoogle(defaultGoogle);
    setConnectDialogOpen(false);
    setGoogleSessionIconGeneration((n) => n + 1);
  }, [projectId, isAuthenticated]);

  const openGoogleTestConnect = useCallback(() => {
    setConnectDialogOpen(true);
  }, []);

  const openTestSignInLearnMore = useCallback(() => {
    setTestSignInLearnMoreOpen(true);
  }, []);

  const handleGsiBusy = useCallback(() => {
    setGoogle((prev) => ({ ...prev, status: "connecting" }));
  }, []);

  const handleGsiSuccess = useCallback(
    (detail: {
      connected_as?: string | null;
      session_display_name?: string | null;
      auth_exchange_url?: string | null;
      captured_at?: string | null;
    }) => {
      let capturedAt: string | undefined;
      if (detail.captured_at) {
        try {
          capturedAt = new Date(detail.captured_at).toLocaleString();
        } catch {
          capturedAt = detail.captured_at;
        }
      }
      setGoogle({
        status: "connected",
        connectedAs: detail.connected_as ?? undefined,
        sessionDisplayName: detail.session_display_name ?? undefined,
        authExchangeUrl: detail.auth_exchange_url ?? undefined,
        capturedAt,
      });
      setConnectDialogOpen(false);
      void refreshAppSessionStatus();
    },
    [refreshAppSessionStatus]
  );

  const handleGsiError = useCallback((_message?: string) => {
    setGoogle({ status: "disconnected" });
    void refreshAppSessionStatus();
  }, [refreshAppSessionStatus]);

  const value = useMemo(
    () => ({
      googleSessionIconGeneration,
      google,
      connectDialogOpen,
      openGoogleTestConnect,
      setConnectDialogOpen,
      startGoogleTestSignIn: openGoogleTestConnect,
      disconnectGoogleTestSession,
      testSignInLearnMoreOpen,
      setTestSignInLearnMoreOpen,
      openTestSignInLearnMore,
      refreshAppSessionStatus,
    }),
    [
      googleSessionIconGeneration,
      google,
      connectDialogOpen,
      openGoogleTestConnect,
      disconnectGoogleTestSession,
      testSignInLearnMoreOpen,
      openTestSignInLearnMore,
      refreshAppSessionStatus,
    ]
  );

  return (
    <TestGoogleSessionContext.Provider value={value}>
      {children}
      <GoogleTestConnectDialog
        open={connectDialogOpen}
        onOpenChange={setConnectDialogOpen}
        google={google}
        googleSessionIconGeneration={googleSessionIconGeneration}
        projectId={projectId}
        onGsiBusy={handleGsiBusy}
        onGsiSuccess={handleGsiSuccess}
        onGsiError={handleGsiError}
        onDisconnect={disconnectGoogleTestSession}
      />
      <TestSignInLearnMoreDialog
        open={testSignInLearnMoreOpen}
        onOpenChange={setTestSignInLearnMoreOpen}
      />
    </TestGoogleSessionContext.Provider>
  );
}
