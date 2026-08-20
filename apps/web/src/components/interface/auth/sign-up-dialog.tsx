"use client";

import React, { useState } from "react";
import { cn } from "@/lib/utils";
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
import { Github, UserRoundPen, Eye, EyeOff, AlertCircle } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { GoogleIcon } from "./icons";
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

export interface SignUpPanelProps {
  onSignUp: (email: string, password: string, displayName: string) => void;
  onGitHubSignUp: () => void;
  onGoogleSignUp: () => void;
  onShowSignIn: () => void;
  isSubmitting?: boolean;
  error?: string | null;
  className?: string;
  titleId?: string;
  descriptionId?: string;
  /** `page` = full-width auth screen (large title, no icon). `modal` = compact header with icon. */
  headingLayout?: "modal" | "page";
}

function PasswordRule({ valid, text }: { valid: boolean; text: string }) {
  return (
    <div className="flex items-center gap-2 text-[10px]">
      <div className={cn("h-1.5 w-1.5 rounded-full", valid ? "bg-[#10b981]" : "bg-[#888888]")} />
      <span className={cn(valid ? "text-[#10b981]" : "text-[#888888]")}>{text}</span>
    </div>
  );
}

export function SignUpPanel({
  onSignUp,
  onGitHubSignUp,
  onGoogleSignUp,
  onShowSignIn,
  isSubmitting = false,
  error = null,
  className,
  titleId = "sign-up-title",
  descriptionId = "sign-up-desc",
  headingLayout = "modal",
}: SignUpPanelProps) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const passwordValidation = {
    minLength: password.length >= 8,
    hasUpperCase: /[A-Z]/.test(password),
    hasLowerCase: /[a-z]/.test(password),
    hasNumber: /[0-9]/.test(password),
    hasSpecialChar: /[!@#$%^&*(),.?":{}|<>]/.test(password),
  };

  const isPasswordValid = Object.values(passwordValidation).every(Boolean);

  const handleEmailSignUp = (e: React.FormEvent) => {
    e.preventDefault();
    if (email && isPasswordValid && name) {
      onSignUp(email, password, name);
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
            Create account
          </h1>
          <p id={descriptionId} className="mt-1.5 max-w-md text-[13px] leading-relaxed text-[#888888]">
            Get started — create an account to import projects and run your workspace.
          </p>
        </header>
      ) : (
        <div className="flex items-center gap-3 mb-2">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-primary to-primary-strong flex items-center justify-center shrink-0">
            <UserRoundPen className="h-5 w-5 text-white" />
          </div>
          <div>
            <h2 id={titleId} className={cn("text-sm font-semibold", authHeadline)}>
              Create Account
            </h2>
            <p id={descriptionId} className={cn("text-xs", authMuted)}>
              Get started with your free account.
            </p>
          </div>
        </div>
      )}

      <div className={cn("space-y-4", headingLayout === "page" ? "mt-0" : "mt-4")}>
        <div className="space-y-2">
          <Button
            type="button"
            onClick={onGitHubSignUp}
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
            onClick={onGoogleSignUp}
            variant="outline"
            data-patchapi-purpose="patchapi-account-google-oauth"
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
            <span className={cn("px-2", authMuted, authOrChipBg)}>Or continue with</span>
          </div>
        </div>

        <form onSubmit={handleEmailSignUp} className="space-y-3">
          <div className="grid gap-2">
            <Label htmlFor={`${titleId}-name`} className={cn("text-xs", authLabel)}>
              First name
            </Label>
            <Input
              id={`${titleId}-name`}
              type="text"
              placeholder="Enter your first name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={cn("h-10 text-sm focus:border-primary focus:ring-primary/20", authField)}
            />
          </div>
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
              className={cn("h-10 text-sm focus:border-primary focus:ring-primary/20", authField)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor={`${titleId}-password`} className={cn("text-xs", authLabel)}>
              Password
            </Label>
            <div className="relative">
              <Input
                id={`${titleId}-password`}
                type={showPassword ? "text" : "password"}
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
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
            {password && (
              <div className="space-y-1.5 mt-2">
                <PasswordRule valid={passwordValidation.minLength} text="At least 8 characters in length" />
                <PasswordRule valid={passwordValidation.hasUpperCase} text="Contains at least one uppercase letter" />
                <PasswordRule valid={passwordValidation.hasLowerCase} text="Contains at least one lowercase letter" />
                <PasswordRule valid={passwordValidation.hasNumber} text="Contains at least one number" />
                <PasswordRule valid={passwordValidation.hasSpecialChar} text="Contains at least one special character" />
              </div>
            )}
          </div>

          {error && (
            <div className="flex items-center gap-2">
              <AlertCircle className="h-3.5 w-3.5 text-red-400 flex-shrink-0" />
              <p className="text-[10px] text-red-400">{error}</p>
            </div>
          )}

          <Button
            type="submit"
            disabled={isSubmitting || !isPasswordValid || !email || !name}
            className="w-full bg-primary hover:bg-primary-hover text-primary-foreground text-sm shadow-sm h-10 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? (
              <>
                <Spinner className="h-4 w-4 mr-2" />
                Creating account...
              </>
            ) : (
              "Create Account"
            )}
          </Button>
        </form>

        <div className={cn("text-center text-xs", authMuted)}>
          Already have an account?{" "}
          <button type="button" onClick={onShowSignIn} className="text-primary hover:underline font-medium">
            Sign in
          </button>
        </div>
      </div>
    </div>
  );
}

interface SignUpDialogProps extends SignUpPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SignUpDialog({
  open,
  onOpenChange,
  onSignUp,
  onGitHubSignUp,
  onGoogleSignUp,
  onShowSignIn,
  isSubmitting = false,
  error = null,
  headingLayout = "modal",
}: SignUpDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={authModalContent}
        aria-labelledby="sign-up-dialog-title"
        aria-describedby="sign-up-dialog-desc"
      >
        <DialogHeader className="sr-only">
          <DialogTitle id="sign-up-dialog-title">Create Account</DialogTitle>
          <DialogDescription id="sign-up-dialog-desc">
            Sign up with GitHub, Google, or email and password.
          </DialogDescription>
        </DialogHeader>
        <SignUpPanel
          titleId="sign-up-dialog-fields-title"
          descriptionId="sign-up-dialog-fields-desc"
          headingLayout={headingLayout}
          onSignUp={onSignUp}
          onGitHubSignUp={onGitHubSignUp}
          onGoogleSignUp={onGoogleSignUp}
          onShowSignIn={() => {
            onOpenChange(false);
            onShowSignIn();
          }}
          isSubmitting={isSubmitting}
          error={error}
        />
      </DialogContent>
    </Dialog>
  );
}
