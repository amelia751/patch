"use client";

import React, { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Github, UserRoundCheck, Eye, EyeOff, AlertCircle } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { GoogleIcon } from "./icons";
import { cn } from "@/lib/utils";
import {
  authDividerLine,
  authField,
  authHeadline,
  authIconButtonMuted,
  authLabel,
  authModalContent,
  authMuted,
  authOrChipBg,
  authOutlineButton,
} from "./auth-surface";

export interface SignInPanelProps {
  onSignIn: (email: string, password: string) => void;
  onGitHubSignIn: () => void;
  onGoogleSignIn: () => void;
  onShowSignUp: () => void;
  onShowForgotPassword?: () => void;
  isSubmitting?: boolean;
  error?: string | null;
  className?: string;
  titleId?: string;
  descriptionId?: string;
  /** Background for the “Or continue with” chip (match the surrounding card). */
  orChipClassName?: string;
  /** `page` = full-width auth screen (large title, no icon). `modal` = compact header with icon. */
  headingLayout?: "modal" | "page";
}

export function SignInPanel({
  onSignIn,
  onGitHubSignIn,
  onGoogleSignIn,
  onShowSignUp,
  onShowForgotPassword,
  isSubmitting = false,
  error = null,
  className,
  titleId = "sign-in-title",
  descriptionId = "sign-in-desc",
  orChipClassName = authOrChipBg,
  headingLayout = "modal",
}: SignInPanelProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const handleEmailSignIn = (e: React.FormEvent) => {
    e.preventDefault();
    if (email && password) {
      onSignIn(email, password);
    }
  };

  return (
    <div className={cn("space-y-0", className)}>
      {headingLayout === "page" ? (
        <header className="mb-6">
          <h1
            id={titleId}
            className="text-lg font-medium tracking-tight text-[#e8e8e8] md:text-xl"
          >
            Sign in
          </h1>
          <p id={descriptionId} className="mt-1.5 max-w-md text-[13px] leading-relaxed text-[#888888]">
            Welcome back — sign in to continue to your workspace.
          </p>
        </header>
      ) : (
        <div className="flex items-center gap-3 mb-2">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-primary to-primary-strong flex items-center justify-center shrink-0">
            <UserRoundCheck className="h-5 w-5 text-white" />
          </div>
          <div>
            <h2 id={titleId} className={cn("text-sm font-semibold", authHeadline)}>
              Sign In
            </h2>
            <p id={descriptionId} className={cn("text-xs", authMuted)}>
              Welcome back! Please sign in to continue.
            </p>
          </div>
        </div>
      )}

      <div className={cn("space-y-4", headingLayout === "page" ? "mt-0" : "mt-4")}>
        <div className="space-y-2">
          <Button
            type="button"
            onClick={onGitHubSignIn}
            variant="outline"
            className={cn(
              "w-full h-10 text-sm flex items-center justify-center gap-2",
              authOutlineButton
            )}
          >
            <Github className="h-4 w-4" />
            Continue with GitHub
          </Button>
          <Button
            type="button"
            onClick={onGoogleSignIn}
            variant="outline"
            data-jetrun-purpose="jetrun-account-google-oauth"
            className={cn(
              "w-full h-10 text-sm flex items-center justify-center gap-2",
              authOutlineButton
            )}
          >
            <GoogleIcon className="h-4 w-4" />
            Continue with Google
          </Button>
        </div>

        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <span className={cn("w-full border-t", authDividerLine)} />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className={cn("px-2", authMuted, orChipClassName)}>Or continue with</span>
          </div>
        </div>

        <form onSubmit={handleEmailSignIn} className="space-y-3">
          <div className="grid gap-2">
            <Label htmlFor={`${titleId}-email`} className={cn("text-xs", authLabel)}>
              Email
            </Label>
            <Input
              id={`${titleId}-email`}
              type="email"
              placeholder="Enter your email address"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              className={cn("h-10 text-sm focus:border-primary focus:ring-primary/20", authField)}
            />
          </div>
          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <Label htmlFor={`${titleId}-password`} className={cn("text-xs", authLabel)}>
                Password
              </Label>
              {onShowForgotPassword && (
                <button
                  type="button"
                  onClick={onShowForgotPassword}
                  className="text-[10px] text-primary hover:underline font-medium"
                >
                  Forgot password?
                </button>
              )}
            </div>
            <div className="relative">
              <Input
                id={`${titleId}-password`}
                type={showPassword ? "text" : "password"}
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                className={cn(
                  "h-10 text-sm focus:border-primary focus:ring-primary/20 pr-10",
                  authField
                )}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className={cn(
                  "absolute right-3 top-1/2 -translate-y-1/2 transition-colors",
                  authIconButtonMuted
                )}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          {error && (
            <div className="flex items-center gap-2">
              <AlertCircle className="h-3.5 w-3.5 text-red-400 flex-shrink-0" />
              <p className="text-[10px] text-red-400">{error}</p>
            </div>
          )}

          <Button
            type="submit"
            disabled={isSubmitting || !email || !password}
            className="w-full bg-primary hover:bg-primary-hover text-primary-foreground text-sm shadow-sm h-10 disabled:opacity-50"
          >
            {isSubmitting ? (
              <>
                <Spinner className="h-4 w-4 mr-2" />
                Signing in...
              </>
            ) : (
              "Sign In"
            )}
          </Button>
        </form>

        <div className={cn("text-center text-xs", authMuted)}>
          Don&apos;t have an account?{" "}
          <button
            type="button"
            onClick={onShowSignUp}
            className="text-primary hover:underline font-medium"
          >
            Sign up
          </button>
        </div>
      </div>
    </div>
  );
}

interface SignInDialogProps extends SignInPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SignInDialog({
  open,
  onOpenChange,
  onSignIn,
  onGitHubSignIn,
  onGoogleSignIn,
  onShowSignUp,
  onShowForgotPassword,
  isSubmitting = false,
  error = null,
  headingLayout = "modal",
}: SignInDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={authModalContent}
        aria-labelledby="sign-in-dialog-title"
        aria-describedby="sign-in-dialog-desc"
      >
        <DialogHeader className="sr-only">
          <DialogTitle id="sign-in-dialog-title">Sign In</DialogTitle>
          <DialogDescription id="sign-in-dialog-desc">
            Sign in with GitHub, Google, or email and password.
          </DialogDescription>
        </DialogHeader>
        <SignInPanel
          titleId="sign-in-dialog-fields-title"
          descriptionId="sign-in-dialog-fields-desc"
          headingLayout={headingLayout}
          onSignIn={onSignIn}
          onGitHubSignIn={onGitHubSignIn}
          onGoogleSignIn={onGoogleSignIn}
          onShowSignUp={() => {
            onOpenChange(false);
            onShowSignUp();
          }}
          onShowForgotPassword={
            onShowForgotPassword
              ? () => {
                  onOpenChange(false);
                  onShowForgotPassword();
                }
              : undefined
          }
          isSubmitting={isSubmitting}
          error={error}
        />
      </DialogContent>
    </Dialog>
  );
}
