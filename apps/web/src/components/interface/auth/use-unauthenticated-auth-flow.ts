"use client";

import { useState, useCallback, useRef } from "react";
import { useAuth } from "@/lib/auth-context";

export type UseUnauthenticatedAuthFlowOptions = {
  /**
   * When set, flows that would open the sign-in modal instead call this
   * (e.g. root gate inline panel — no modal).
   */
  onSwitchToInlineSignIn?: () => void;
};

/**
 * Shared sign-up / sign-in / verification state for the header trigger and the
 * full-page root auth gate (split layout).
 */
export function useUnauthenticatedAuthFlow(options?: UseUnauthenticatedAuthFlowOptions) {
  const {
    login,
    signup,
    verifyEmail,
    resendVerificationCode,
    forgotPassword,
    resetPassword,
    loginWithGitHub,
    loginWithGoogle,
  } = useAuth();

  const [showSignIn, setShowSignIn] = useState(false);
  const [showSignUp, setShowSignUp] = useState(false);
  const [showVerification, setShowVerification] = useState(false);
  const [showForgotPassword, setShowForgotPassword] = useState(false);
  const [showCheckEmail, setShowCheckEmail] = useState(false);
  const [checkEmailKind, setCheckEmailKind] = useState<"reset" | "verify">("reset");
  const [pendingEmail, setPendingEmail] = useState("");
  const [pendingPassword, setPendingPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  const inlineSignInRef = useRef(options?.onSwitchToInlineSignIn);
  inlineSignInRef.current = options?.onSwitchToInlineSignIn;

  const clearAuthError = useCallback(() => setAuthError(null), []);

  const goToSignIn = useCallback(() => {
    setAuthError(null);
    const inline = inlineSignInRef.current;
    if (inline) inline();
    else setShowSignIn(true);
  }, []);

  const handleEmailSignIn = async (email: string, password: string) => {
    setIsSubmitting(true);
    setAuthError(null);
    try {
      await login(email, password);
      setShowSignIn(false);
      setAuthError(null);
    } catch (error: unknown) {
      console.error("Sign in failed:", error);
      const message =
        error instanceof Error ? error.message : "Invalid email or password. Please try again.";
      setAuthError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleGitHubSignIn = () => {
    loginWithGitHub();
  };

  const handleGoogleSignIn = () => {
    loginWithGoogle();
  };

  const handleSignUp = async (email: string, password: string, displayName: string) => {
    setIsSubmitting(true);
    setAuthError(null);
    try {
      const result = await signup(email, password, displayName);
      setShowSignUp(false);
      setAuthError(null);

      if (result.needsVerification) {
        setPendingEmail(email);
        setPendingPassword(password);
        setShowCheckEmail(true);
      }
    } catch (error: unknown) {
      console.error("Sign up failed:", error);
      const message =
        error instanceof Error ? error.message : "Failed to create account. Please try again.";
      setAuthError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleVerify = async (code: string) => {
    setIsSubmitting(true);
    try {
      await verifyEmail(pendingEmail, code);
      setShowVerification(false);

      if (pendingEmail && pendingPassword) {
        await login(pendingEmail, pendingPassword);
      }

      setPendingEmail("");
      setPendingPassword("");
    } catch (error) {
      console.error("Verification failed:", error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResendCode = async () => {
    if (pendingEmail) {
      try {
        await resendVerificationCode(pendingEmail);
      } catch (error) {
        console.error("Failed to resend code:", error);
      }
    }
  };

  const handleShowSignUp = () => {
    setAuthError(null);
    setShowSignUp(true);
  };

  const handleShowSignIn = goToSignIn;

  const handleShowForgotPassword = () => {
    setAuthError(null);
    setShowForgotPassword(true);
  };

  const handleForgotPassword = async (email: string) => {
    setIsSubmitting(true);
    setAuthError(null);
    try {
      await forgotPassword(email);
      setPendingEmail(email);
      setCheckEmailKind("reset");
      setShowForgotPassword(false);
      setShowCheckEmail(true);
    } catch (error: unknown) {
      console.error("Failed to send reset code:", error);
      const message =
        error instanceof Error ? error.message : "Failed to send reset code";
      setAuthError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResetPassword = async (code: string, newPassword: string) => {
    setIsSubmitting(true);
    setAuthError(null);
    try {
      await resetPassword(pendingEmail, code, newPassword);
      setShowCheckEmail(false);
      setPendingEmail("");
      goToSignIn();
    } catch (error: unknown) {
      console.error("Failed to reset password:", error);
      const message =
        error instanceof Error ? error.message : "Failed to reset password";
      setAuthError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const onSignInOpenChange = (open: boolean) => {
    setShowSignIn(open);
    if (!open) setAuthError(null);
  };

  const onSignUpOpenChange = (open: boolean) => {
    setShowSignUp(open);
    if (!open) setAuthError(null);
  };

  return {
    showSignIn,
    setShowSignIn,
    showSignUp,
    setShowSignUp,
    showVerification,
    setShowVerification,
    showForgotPassword,
    setShowForgotPassword,
    showCheckEmail,
    setShowCheckEmail,
    checkEmailKind,
    pendingEmail,
    setPendingEmail,
    isSubmitting,
    authError,
    clearAuthError,
    handleEmailSignIn,
    handleGitHubSignIn,
    handleGoogleSignIn,
    handleSignUp,
    handleVerify,
    handleResendCode,
    handleShowSignUp,
    handleShowSignIn,
    handleShowForgotPassword,
    handleForgotPassword,
    handleResetPassword,
    onSignInOpenChange,
    onSignUpOpenChange,
  };
}
