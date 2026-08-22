"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { parseAuthAction } from "@/lib/auth-action";
import { cn } from "@/lib/utils";
import { authField, authLabel } from "./auth-surface";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const cardClass =
  "rounded-xl border border-[#2e2e2e] bg-[#1a1a1a] p-6 shadow-2xl md:p-8";

function RuleRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 text-[10px]">
      <div className={cn("h-1.5 w-1.5 rounded-full", ok ? "bg-[#10b981]" : "bg-[#888888]")} />
      <span className={cn(ok ? "text-[#10b981]" : "text-[#888888]")}>{label}</span>
    </div>
  );
}

function goSignIn() {
  window.location.href = "/";
}

export function AuthActionPanel() {
  const search = useSearchParams();
  const [{ mode, oobCode }, setParsed] = useState(() =>
    parseAuthAction(new URLSearchParams(), ""),
  );
  const [accountEmail, setAccountEmail] = useState("");
  const [requestEmail, setRequestEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    setParsed(parseAuthAction(search, typeof window === "undefined" ? "" : window.location.hash));
  }, [search]);

  const rules = useMemo(
    () => ({
      minLength: password.length >= 8,
      hasUpperCase: /[A-Z]/.test(password),
      hasLowerCase: /[a-z]/.test(password),
      hasNumber: /[0-9]/.test(password),
      hasSpecialChar: /[!@#$%^&*(),.?":{}|<>]/.test(password),
    }),
    [password],
  );
  const valid = Object.values(rules).every(Boolean) && password === confirm && confirm.length > 0;
  const isVerify = mode === "verifyEmail";
  const showResetForm = Boolean(oobCode) && !isVerify && !done && !error;

  useEffect(() => {
    if (!oobCode || isVerify || done) return;
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const response = await fetch(`${API_URL}/api/auth/reset-info`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code: oobCode }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.detail || "That reset link is not valid.");
        }
        if (!cancelled) setAccountEmail(typeof payload.email === "string" ? payload.email : "");
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : "That reset link is not valid.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [oobCode, isVerify, done]);

  useEffect(() => {
    if (!isVerify || !oobCode || done) return;
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const response = await fetch(`${API_URL}/api/auth/verify`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code: oobCode }),
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.detail || "Verification failed");
        }
        if (!cancelled) setDone(true);
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : "Verification failed");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isVerify, oobCode, done]);

  async function onReset(event: FormEvent) {
    event.preventDefault();
    if (!valid || !oobCode) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: oobCode, new_password: password }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "Failed to reset password");
      }
      setDone(true);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Failed to reset password");
    } finally {
      setSubmitting(false);
    }
  }

  async function onRequestReset(event: FormEvent) {
    event.preventDefault();
    if (!requestEmail) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email: requestEmail }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "Failed to send reset link");
      }
      setSent(true);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Failed to send reset link");
    } finally {
      setSubmitting(false);
    }
  }

  const title = isVerify ? "Verify email" : "Reset your password";
  const description = done
    ? isVerify
      ? "This address is confirmed. You can sign in."
      : "Your password is updated. You can sign in."
    : showResetForm
      ? accountEmail
        ? `for ${accountEmail}`
        : loading
          ? "Checking this link…"
          : "Choose a new password for this account."
      : isVerify
        ? "This address is confirmed. You can sign in."
        : sent
          ? "If an account exists for that address, we sent a reset link."
          : "Enter your email and we will send a reset link.";

  return (
    <div
      className="min-h-screen w-full flex flex-col md:flex-row"
      style={
        {
          "--bg-primary": "#111111",
          "--bg-secondary": "#1a1a1a",
          "--bg-tertiary": "#222222",
          "--border-color": "#2e2e2e",
          "--text-primary": "#e0e0e0",
          "--text-secondary": "#888888",
          "--text-tertiary": "#ffffff",
        } as React.CSSProperties
      }
    >
      <div className="flex flex-1 flex-col justify-center px-6 py-10 md:w-1/2 md:max-w-[50%] md:px-12 lg:px-16 border-b md:border-b-0 md:border-r border-[#2e2e2e] bg-[#141414]">
        <div className="mx-auto w-full max-w-md">
          <div className={cardClass}>
            <header className="mb-6">
              <h1 className="text-lg font-medium tracking-tight text-[#e8e8e8] md:text-xl">{title}</h1>
              <p className="mt-1.5 max-w-md text-[13px] leading-relaxed text-[#888888]">{description}</p>
            </header>

            {error ? <p className="mb-4 text-sm text-red-400">{error}</p> : null}

            {loading && !showResetForm ? (
              <div className="flex items-center gap-2 text-sm text-[#888888]">
                <Spinner className="h-4 w-4" />
                Working…
              </div>
            ) : null}

            {done || (isVerify && !oobCode) ? (
              <Button
                className="w-full h-10 bg-primary hover:bg-primary-hover text-primary-foreground"
                onClick={goSignIn}
              >
                Sign in
              </Button>
            ) : null}

            {showResetForm ? (
              <form onSubmit={onReset} className="space-y-4">
                <div className="grid gap-2">
                  <Label className={cn("text-xs", authLabel)}>New password</Label>
                  <Input
                    type="password"
                    autoComplete="new-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    className={cn("h-10 text-sm focus:border-primary focus:ring-primary/20", authField)}
                  />
                </div>
                <div className="grid gap-2">
                  <Label className={cn("text-xs", authLabel)}>Confirm password</Label>
                  <Input
                    type="password"
                    autoComplete="new-password"
                    value={confirm}
                    onChange={(event) => setConfirm(event.target.value)}
                    className={cn("h-10 text-sm focus:border-primary focus:ring-primary/20", authField)}
                  />
                </div>
                <div className="grid gap-1">
                  <RuleRow ok={rules.minLength} label="At least 8 characters" />
                  <RuleRow ok={rules.hasUpperCase} label="One uppercase letter" />
                  <RuleRow ok={rules.hasLowerCase} label="One lowercase letter" />
                  <RuleRow ok={rules.hasNumber} label="One number" />
                  <RuleRow ok={rules.hasSpecialChar} label="One special character" />
                  <RuleRow ok={password === confirm && confirm.length > 0} label="Passwords match" />
                </div>
                <Button
                  type="submit"
                  disabled={!valid || submitting || loading}
                  className="w-full h-10 bg-primary hover:bg-primary-hover text-primary-foreground text-sm shadow-sm disabled:opacity-50"
                >
                  {submitting ? <Spinner className="h-4 w-4 mr-2" /> : null}
                  Save
                </Button>
              </form>
            ) : null}

            {!done && !isVerify && !showResetForm ? (
              <form onSubmit={onRequestReset} className="space-y-4">
                <div className="grid gap-2">
                  <Label className={cn("text-xs", authLabel)}>Email</Label>
                  <Input
                    type="email"
                    autoComplete="email"
                    placeholder="Enter your email address"
                    value={requestEmail}
                    onChange={(event) => setRequestEmail(event.target.value)}
                    className={cn("h-10 text-sm focus:border-primary focus:ring-primary/20", authField)}
                  />
                </div>
                <Button
                  type="submit"
                  disabled={submitting || !requestEmail || sent}
                  className="w-full h-10 bg-primary hover:bg-primary-hover text-primary-foreground text-sm shadow-sm disabled:opacity-50"
                >
                  {submitting ? <Spinner className="h-4 w-4 mr-2" /> : null}
                  {sent ? "Link sent" : "Send reset link"}
                </Button>
                <p className="text-center text-xs text-[#888888]">
                  Remember your password?{" "}
                  <button type="button" onClick={goSignIn} className="text-primary hover:underline font-medium">
                    Sign in
                  </button>
                </p>
              </form>
            ) : null}
          </div>
        </div>
      </div>

      <div className="relative flex flex-1 min-h-[40vh] md:min-h-0 md:w-1/2 overflow-hidden" aria-hidden>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/space.png"
          alt=""
          className="absolute inset-0 h-full w-full object-cover object-center"
          style={{ filter: "saturate(0.75) brightness(0.9)" }}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-black/10" />
      </div>
    </div>
  );
}
