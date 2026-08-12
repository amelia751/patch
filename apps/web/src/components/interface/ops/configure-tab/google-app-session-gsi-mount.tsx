"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const GCP_CREDENTIALS_FALLBACK = "https://console.cloud.google.com/apis/credentials";

/**
 * Web OAuth client IDs are `{project_number}-{suffix}.apps.googleusercontent.com`.
 * Console accepts that number in `?project=` to open the right GCP project's Credentials page.
 */
function gcpCredentialsConsoleUrl(googleOAuthClientId: string | null): string {
  if (!googleOAuthClientId?.trim()) return GCP_CREDENTIALS_FALLBACK;
  const m = /^(\d+)-.+\.apps\.googleusercontent\.com$/i.exec(
    googleOAuthClientId.trim()
  );
  if (!m) return GCP_CREDENTIALS_FALLBACK;
  return `${GCP_CREDENTIALS_FALLBACK}?project=${encodeURIComponent(m[1])}`;
}

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (resp: { credential: string }) => void;
            auto_select?: boolean;
            cancel_on_tap_outside?: boolean;
            use_fedcm_for_prompt?: boolean;
            use_fedcm_for_button?: boolean;
          }) => void;
          renderButton: (
            parent: HTMLElement,
            options: { theme?: string; size?: string; width?: string | number; text?: string; type?: string }
          ) => void;
        };
      };
    };
  }
}

function loadGsiScript(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject();
  if (window.google?.accounts?.id) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const existing = document.querySelector('script[src="https://accounts.google.com/gsi/client"]');
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("GSI script error")));
      return;
    }
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.defer = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Failed to load Google Identity Services"));
    document.head.appendChild(s);
  });
}

export interface GoogleAppSessionGsiMountProps {
  projectId: string;
  onExchangeSuccess: (detail: {
    connected_as?: string | null;
    session_display_name?: string | null;
    auth_exchange_url?: string | null;
    captured_at?: string | null;
  }) => void;
  onExchangeError: (message: string) => void;
  onBusy: () => void;
  onNavigateToConfigureSecrets?: () => void;
  className?: string;
}

function isOpsPath(pathname: string | null): boolean {
  if (!pathname) return false;
  return pathname === "/ops" || pathname.endsWith("/ops");
}

function isMainWorkspacePath(pathname: string | null): boolean {
  return pathname === "/" || pathname === "";
}

function navigateToConfigureSecrets(
  router: ReturnType<typeof useRouter>,
  pathname: string | null
) {
  const p = new URLSearchParams(
    typeof window !== "undefined" ? window.location.search : ""
  );
  p.set("configureSection", "secrets");
  p.delete("tab");
  const qs = p.toString();

  if (isOpsPath(pathname)) {
    const base = pathname ?? "/ops";
    router.replace(`${base}?${qs}`);
    return;
  }

  if (isMainWorkspacePath(pathname)) {
    router.replace(`/?${qs}`);
    return;
  }

  router.replace(`/?${qs}`);
}

export function GoogleAppSessionGsiMount({
  projectId,
  onExchangeSuccess,
  onExchangeError,
  onBusy,
  onNavigateToConfigureSecrets,
  className,
}: GoogleAppSessionGsiMountProps) {
  const router = useRouter();
  const pathname = usePathname();
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [clientId, setClientId] = useState<string | null>(null);
  const [clientIdMissing, setClientIdMissing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [exchangeUrlDisplay, setExchangeUrlDisplay] = useState<string | null>(null);
  const [exchangeUrlMissing, setExchangeUrlMissing] = useState(false);
  const authExchangeUrlRef = useRef<string | null>(null);
  const successRef = useRef(onExchangeSuccess);
  const errorRef = useRef(onExchangeError);
  const busyRef = useRef(onBusy);
  successRef.current = onExchangeSuccess;
  errorRef.current = onExchangeError;
  busyRef.current = onBusy;

  useEffect(() => {
    let cancelled = false;

    async function setup() {
      setError(null);
      setClientIdMissing(false);
      setExchangeUrlMissing(false);
      setLoading(true);
      try {
        const cfgRes = await fetch(
          `${API_URL}/api/projects/${projectId}/app-session/google-signin-config`,
          { credentials: "include" }
        );
        if (!cfgRes.ok) throw new Error("Could not load Google sign-in configuration");
        const cfg = await cfgRes.json();
        const cid = cfg.client_id as string | undefined;
        if (!cid) {
          setClientIdMissing(true);
          setLoading(false);
          return;
        }
        if (cancelled) return;
        setClientId(cid);

        if (!cfg.has_custom_exchange_url || !cfg.auth_exchange_url) {
          setExchangeUrlMissing(true);
          setLoading(false);
          return;
        }

        authExchangeUrlRef.current = cfg.auth_exchange_url as string;
        setExchangeUrlDisplay(cfg.auth_exchange_url as string);

        await loadGsiScript();
        if (cancelled || !containerRef.current) return;

        const id = window.google?.accounts?.id;
        if (!id) {
          setError("Google Identity Services failed to initialize.");
          setLoading(false);
          return;
        }

        id.initialize({
          client_id: cid,
          use_fedcm_for_prompt: false,
          use_fedcm_for_button: false,
          callback: async (resp) => {
            if (!resp?.credential) {
              errorRef.current("No credential from Google");
              return;
            }
            busyRef.current();
            try {
              const exchangeBody: Record<string, string> = { credential: resp.credential };
              if (authExchangeUrlRef.current) {
                exchangeBody.auth_exchange_url = authExchangeUrlRef.current;
              }
              const res = await fetch(`${API_URL}/api/projects/${projectId}/app-session/exchange`, {
                method: "POST",
                credentials: "include",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(exchangeBody),
              });
              const text = await res.text();
              let data: Record<string, unknown> = {};
              try {
                data = text ? JSON.parse(text) : {};
              } catch {
                /* ignore */
              }
              if (!res.ok) {
                const detail = (data.detail as string) || text || res.statusText;
                throw new Error(typeof detail === "string" ? detail : "Exchange failed");
              }
              successRef.current({
                connected_as: data.connected_as as string | undefined,
                session_display_name: data.session_display_name as string | undefined,
                auth_exchange_url: data.auth_exchange_url as string | undefined,
                captured_at: data.captured_at as string | undefined,
              });
            } catch (e) {
              setError(e instanceof Error ? e.message : "Exchange failed");
              errorRef.current(e instanceof Error ? e.message : "Exchange failed");
            }
          },
          auto_select: false,
          cancel_on_tap_outside: true,
        });

        containerRef.current.innerHTML = "";
        id.renderButton(containerRef.current, {
          theme: "outline",
          size: "large",
          width: "100%",
          text: "continue_with",
          type: "standard",
        });
        setLoading(false);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Could not start Google sign-in");
          setLoading(false);
        }
      }
    }

    void setup();
    return () => { cancelled = true; };
  }, [projectId]);

  if (clientIdMissing) {
    return (
      <div
        className={cn(
          "flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-left",
          className
        )}
      >
        <AlertCircle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" aria-hidden />
        <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
          Add{" "}
          <code className="rounded bg-[var(--bg-tertiary)] px-1 py-0.5 text-[10px] text-[var(--text-primary)]">
            GOOGLE_CLIENT_ID
          </code>{" "}
          to project secrets (
          <button
            type="button"
            className={cn(
              "font-medium text-[var(--text-primary)]",
              "underline-offset-2 decoration-from-font",
              "decoration-transparent hover:underline hover:decoration-[var(--text-primary)]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-1 rounded-sm"
            )}
            onClick={() => {
              onNavigateToConfigureSecrets?.();
              navigateToConfigureSecrets(router, pathname);
            }}
          >
            Configure &rarr; Secrets
          </button>
          ), then try again.
        </p>
      </div>
    );
  }

  if (exchangeUrlMissing) {
    return (
      <div
        className={cn(
          "flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-left",
          className
        )}
      >
        <AlertCircle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" aria-hidden />
        <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
          Add{" "}
          <code className="rounded bg-[var(--bg-tertiary)] px-1 py-0.5 text-[10px] text-[var(--text-primary)]">
            AUTH_EXCHANGE_URL
          </code>{" "}
          to project secrets — your app&apos;s Google auth endpoint (e.g.{" "}
          <code className="text-[10px] font-mono">
            https://api.example.com/auth/google
          </code>{" "}
          or{" "}
          <code className="text-[10px] font-mono">
            http://localhost:3000/api/auth/google
          </code>
          ).{" "}
          <button
            type="button"
            className={cn(
              "font-medium text-[var(--text-primary)]",
              "underline-offset-2 decoration-from-font",
              "decoration-transparent hover:underline hover:decoration-[var(--text-primary)]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:ring-offset-1 rounded-sm"
            )}
            onClick={() => {
              onNavigateToConfigureSecrets?.();
              navigateToConfigureSecrets(router, pathname);
            }}
          >
            Configure &rarr; Secrets
          </button>
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className={cn(
          "flex items-start gap-2 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-left",
          className
        )}
      >
        <AlertCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" aria-hidden />
        <div className="text-[11px] text-[var(--text-secondary)] leading-relaxed space-y-1.5">
          <p>{error}</p>
          {clientId ? (
            <p>
              <a
                href={gcpCredentialsConsoleUrl(clientId)}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-[var(--text-primary)] underline underline-offset-2"
              >
                Open Google Cloud credentials for this client ID
              </a>
            </p>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className={cn("w-full min-h-[40px] flex flex-col items-stretch gap-2", className)}>
      {loading ? (
        <div className="h-10 flex items-center justify-center text-[11px] text-[var(--text-secondary)]">
          Preparing Google sign-in&hellip;
        </div>
      ) : null}
      <div ref={containerRef} className="w-full flex justify-center [&>div]:!w-full" />
      {!loading && (
        <div className="space-y-1.5">
          {exchangeUrlDisplay ? (
            <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed text-center">
              Credential will be sent to{" "}
              <code className="rounded bg-[var(--bg-tertiary)] px-1 py-0.5 text-[9px] text-[var(--text-primary)] font-mono">
                {exchangeUrlDisplay}
              </code>
              {exchangeUrlDisplay.includes("localhost") || exchangeUrlDisplay.includes("127.0.0.1")
                ? " (via sandbox)"
                : null}
            </p>
          ) : null}
          <p className="text-[10px] text-[var(--text-tertiary)] leading-relaxed text-center">
            Ensure{" "}
            <code className="rounded bg-[var(--bg-tertiary)] px-1 py-0.5 text-[9px] text-[var(--text-secondary)]">
              {typeof window !== "undefined" ? window.location.origin : "https://app.jetrun.sh"}
            </code>{" "}
            is added as an{" "}
            <a
              href={gcpCredentialsConsoleUrl(clientId)}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--text-secondary)] underline underline-offset-2"
            >
              authorized JavaScript origin
            </a>{" "}
            in your Google Cloud Console for the client ID above.
          </p>
        </div>
      )}
    </div>
  );
}
