"use client";

import { useState, useCallback } from "react";
import { SignInPanel } from "./sign-in-dialog";
import { SignUpPanel } from "./sign-up-dialog";
import { EmailVerificationDialog } from "./email-verification-dialog";
import { ForgotPasswordDialog } from "./forgot-password-dialog";
import { CheckEmailDialog } from "./check-email-dialog";
import { useUnauthenticatedAuthFlow } from "./use-unauthenticated-auth-flow";
import { cn } from "@/lib/utils";

interface RootAuthGateProps {
  className?: string;
}

const cardClass =
  "rounded-xl border border-[#2e2e2e] bg-[#1a1a1a] p-6 shadow-2xl md:p-8";

/**
 * Full-viewport split sign-in for `/` when logged out: same controls as the
 * header modal, with a placeholder hero panel for future art.
 */
export function RootAuthGate({ className }: RootAuthGateProps) {
  const [gateStep, setGateStep] = useState<"signin" | "signup">("signin");
  const switchToSignIn = useCallback(() => setGateStep("signin"), []);
  const switchToSignUp = useCallback(() => setGateStep("signup"), []);

  const flow = useUnauthenticatedAuthFlow({
    onSwitchToInlineSignIn: switchToSignIn,
  });

  return (
    <div
      className={cn("min-h-screen w-full flex flex-col md:flex-row", className)}
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
          {gateStep === "signin" ? (
            <SignInPanel
              titleId="root-gate-sign-in-title"
              descriptionId="root-gate-sign-in-desc"
              headingLayout="page"
              onSignIn={flow.handleEmailSignIn}
              onGitHubSignIn={flow.handleGitHubSignIn}
              onGoogleSignIn={flow.handleGoogleSignIn}
              onShowSignUp={() => {
                flow.clearAuthError();
                switchToSignUp();
              }}
              onShowForgotPassword={flow.handleShowForgotPassword}
              isSubmitting={flow.isSubmitting}
              error={flow.authError}
              className={cardClass}
            />
          ) : (
            <SignUpPanel
              titleId="root-gate-sign-up-title"
              descriptionId="root-gate-sign-up-desc"
              headingLayout="page"
              onSignUp={flow.handleSignUp}
              onGitHubSignUp={flow.handleGitHubSignIn}
              onGoogleSignUp={flow.handleGoogleSignIn}
              onShowSignIn={() => {
                flow.clearAuthError();
                switchToSignIn();
              }}
              isSubmitting={flow.isSubmitting}
              error={flow.authError}
              className={cardClass}
            />
          )}
        </div>
      </div>

      <div
        className="relative flex flex-1 min-h-[40vh] md:min-h-0 md:w-1/2 overflow-hidden"
        aria-hidden
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/space.png"
          alt=""
          className="absolute inset-0 h-full w-full object-cover object-center"
          style={{ filter: "saturate(0.75) brightness(0.9)" }}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />
      </div>

      <EmailVerificationDialog
        open={flow.showVerification}
        onOpenChange={flow.setShowVerification}
        onVerify={flow.handleVerify}
        onResend={flow.handleResendCode}
        email={flow.pendingEmail}
        isSubmitting={flow.isSubmitting}
      />
      <ForgotPasswordDialog
        open={flow.showForgotPassword}
        onOpenChange={flow.setShowForgotPassword}
        onSubmit={flow.handleForgotPassword}
        onShowSignIn={flow.handleShowSignIn}
        isSubmitting={flow.isSubmitting}
        error={flow.authError}
      />
      <CheckEmailDialog
        open={flow.showCheckEmail}
        onOpenChange={flow.setShowCheckEmail}
        email={flow.pendingEmail}
        onShowSignIn={flow.handleShowSignIn}
        description={
          flow.checkEmailKind === "verify"
            ? "We sent a verification link. Open it to confirm this address."
            : "If an account exists for that address, we sent a reset link. Open it to choose a new password."
        }
      />
    </div>
  );
}
