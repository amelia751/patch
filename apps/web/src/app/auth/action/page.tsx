"use client";

import { FormEvent, Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function RuleRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 text-[10px]">
      <div className={cn("h-1.5 w-1.5 rounded-full", ok ? "bg-[#10b981]" : "bg-[#888888]")} />
      <span className={cn(ok ? "text-[#10b981]" : "text-[#888888]")}>{label}</span>
    </div>
  );
}

function ActionInner() {
  const params = useSearchParams();
  const mode = params.get("mode") || "";
  const oobCode = params.get("oobCode") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [verifying, setVerifying] = useState(false);

  const rules = useMemo(
    () => ({
      minLength: password.length >= 8,
      hasUpperCase: /[A-Z]/.test(password),
      hasLowerCase: /[a-z]/.test(password),
      hasNumber: /[0-9]/.test(password),
      hasSpecialChar: /[!@#$%^&*(),.?":{}|<>]/.test(password),
    }),
    [password]
  );
  const valid = Object.values(rules).every(Boolean) && password === confirm && confirm.length > 0;

  async function applyVerify() {
    if (!oobCode) {
      setError("This verification link is missing its code.");
      setVerifying(false);
      return;
    }
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
      setDone(true);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Verification failed");
    } finally {
      setVerifying(false);
    }
  }

  useEffect(() => {
    if (mode !== "verifyEmail" || done || error) return;
    setVerifying(true);
    void applyVerify();
    // The oobCode is the only input; re-running would consume it twice.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, oobCode]);

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

  const heading =
    mode === "verifyEmail"
      ? "Verify email"
      : mode === "resetPassword"
        ? "Reset password"
        : "Continue";

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#111111] px-6 py-12">
      <div className="w-full max-w-md rounded-xl border border-[#2e2e2e] bg-[#1a1a1a] p-6 shadow-2xl">
        <h1 className="text-lg font-semibold text-[#e0e0e0]">{heading}</h1>
        <p className="mt-1 text-xs text-[#888888]">
          {done
            ? "You can sign in now."
            : mode === "resetPassword" && oobCode
              ? "Choose a new password for this account."
              : mode === "resetPassword"
                ? "If you already chose a new password on the previous page, you can sign in."
                : mode === "verifyEmail"
                  ? "Confirming this address."
                  : "This link is missing a reset or verification code."}
        </p>

        {error ? <p className="mt-4 text-sm text-red-400">{error}</p> : null}

        {done ? (
          <Button
            className="mt-6 w-full h-10 bg-primary text-primary-foreground"
            onClick={() => {
              window.location.href = "/?auth=success";
            }}
          >
            Sign in
          </Button>
        ) : null}

        {!done && mode === "resetPassword" && !oobCode ? (
          <Button
            className="mt-6 w-full h-10 bg-primary text-primary-foreground"
            onClick={() => {
              window.location.href = "/?auth=success";
            }}
          >
            Sign in
          </Button>
        ) : null}

        {!done && mode === "resetPassword" && oobCode ? (
          <form onSubmit={onReset} className="mt-6 space-y-4">
            <div className="grid gap-2">
              <Label className="text-xs text-[#888888]">New password</Label>
              <Input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="h-10 bg-[#111111] border-[#2e2e2e] text-[#e0e0e0]"
              />
            </div>
            <div className="grid gap-2">
              <Label className="text-xs text-[#888888]">Confirm password</Label>
              <Input
                type="password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                className="h-10 bg-[#111111] border-[#2e2e2e] text-[#e0e0e0]"
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
              disabled={!valid || submitting || !oobCode}
              className="w-full h-10 bg-primary text-primary-foreground disabled:opacity-50"
            >
              {submitting ? <Spinner className="h-4 w-4 mr-2" /> : null}
              Save password
            </Button>
          </form>
        ) : null}

        {verifying ? (
          <div className="mt-6 flex items-center gap-2 text-sm text-[#888888]">
            <Spinner className="h-4 w-4" />
            Verifying…
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default function AuthActionPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-[#111111] text-[#888888]">
          Loading…
        </div>
      }
    >
      <ActionInner />
    </Suspense>
  );
}
