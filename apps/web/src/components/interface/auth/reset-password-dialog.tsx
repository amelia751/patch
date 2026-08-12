"use client";

import React, { useState, useRef } from "react";
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
import { Key, Eye, EyeOff } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import {
  authField,
  authHeadline,
  authIconButtonMuted,
  authLabel,
  authModalContent,
  authMuted,
} from "./auth-surface";

interface ResetPasswordDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (code: string, newPassword: string) => void;
  onResend: () => void;
  email: string;
  isSubmitting?: boolean;
}

function RuleRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 text-[10px]">
      <div className={cn("h-1.5 w-1.5 rounded-full", ok ? "bg-[#10b981]" : "bg-[#888888]")} />
      <span className={cn(ok ? "text-[#10b981]" : "text-[#888888]")}>{label}</span>
    </div>
  );
}

export function ResetPasswordDialog({
  open,
  onOpenChange,
  onSubmit,
  onResend,
  email,
  isSubmitting = false,
}: ResetPasswordDialogProps) {
  const [code, setCode] = useState(["", "", "", "", "", ""]);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  const passwordValidation = {
    minLength: newPassword.length >= 8,
    hasUpperCase: /[A-Z]/.test(newPassword),
    hasLowerCase: /[a-z]/.test(newPassword),
    hasNumber: /[0-9]/.test(newPassword),
    hasSpecialChar: /[!@#$%^&*(),.?":{}|<>]/.test(newPassword),
  };

  const isPasswordValid = Object.values(passwordValidation).every(Boolean);
  const passwordsMatch = newPassword === confirmPassword && confirmPassword.length > 0;
  const codeComplete = code.every((digit) => digit !== "");

  const handleCodeChange = (index: number, value: string) => {
    if (value && !/^\d$/.test(value)) return;

    const newCode = [...code];
    newCode[index] = value;
    setCode(newCode);

    if (value && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !code[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault();
    const pastedData = e.clipboardData.getData("text").slice(0, 6);
    const digits = pastedData.split("").filter((char) => /^\d$/.test(char));

    const newCode = [...code];
    digits.forEach((digit, index) => {
      if (index < 6) {
        newCode[index] = digit;
      }
    });
    setCode(newCode);

    const nextEmptyIndex = newCode.findIndex((digit) => digit === "");
    if (nextEmptyIndex !== -1) {
      inputRefs.current[nextEmptyIndex]?.focus();
    } else {
      inputRefs.current[5]?.focus();
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const codeString = code.join("");
    if (codeComplete && newPassword && isPasswordValid && passwordsMatch) {
      onSubmit(codeString, newPassword);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={authModalContent}>
        <DialogHeader>
          <div className="flex items-center gap-3 mb-2">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-primary to-primary-strong flex items-center justify-center">
              <Key className="h-5 w-5 text-white" />
            </div>
            <div>
              <DialogTitle className={cn("text-sm font-semibold", authHeadline)}>
                Reset Password
              </DialogTitle>
              <DialogDescription className={cn("text-xs", authMuted)}>
                We sent a reset code to {email}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 mt-4">
          <div className="grid gap-2">
            <Label className={cn("text-xs", authLabel)}>Reset Code</Label>
            <div className="flex gap-2 justify-center" onPaste={handlePaste}>
              {code.map((digit, index) => (
                <Input
                  key={index}
                  ref={(el) => {
                    inputRefs.current[index] = el;
                  }}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  onChange={(e) => handleCodeChange(index, e.target.value)}
                  onKeyDown={(e) => handleKeyDown(index, e)}
                  className={cn(
                    "h-12 w-12 text-center text-lg font-semibold focus:border-primary focus:ring-primary/20",
                    authField
                  )}
                />
              ))}
            </div>
          </div>

          <div className="grid gap-2">
            <Label className={cn("text-xs", authLabel)}>New Password</Label>
            <div className="relative">
              <Input
                type={showPassword ? "text" : "password"}
                placeholder="Enter your new password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
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
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {newPassword && (
              <div className="space-y-1.5 mt-2">
                <RuleRow ok={passwordValidation.minLength} label="At least 8 characters in length" />
                <RuleRow ok={passwordValidation.hasUpperCase} label="Contains at least one uppercase letter" />
                <RuleRow ok={passwordValidation.hasLowerCase} label="Contains at least one lowercase letter" />
                <RuleRow ok={passwordValidation.hasNumber} label="Contains at least one number" />
                <RuleRow ok={passwordValidation.hasSpecialChar} label="Contains at least one special character" />
              </div>
            )}
          </div>

          <div className="grid gap-2">
            <Label className={cn("text-xs", authLabel)}>Confirm Password</Label>
            <div className="relative">
              <Input
                type={showConfirmPassword ? "text" : "password"}
                placeholder="Re-enter your new password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className={cn(
                  "h-10 text-sm focus:border-primary focus:ring-primary/20 pr-10",
                  authField
                )}
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                className={cn(
                  "absolute right-3 top-1/2 -translate-y-1/2 transition-colors",
                  authIconButtonMuted
                )}
              >
                {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {confirmPassword && !passwordsMatch && (
              <p className="text-[10px] text-red-500">Passwords do not match</p>
            )}
            {confirmPassword && passwordsMatch && (
              <p className="text-[10px] text-[#10b981]">Passwords match</p>
            )}
          </div>

          <Button
            type="submit"
            disabled={isSubmitting || !codeComplete || !isPasswordValid || !passwordsMatch}
            className="w-full bg-primary hover:bg-primary-hover text-primary-foreground text-sm shadow-sm h-10 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? (
              <>
                <Spinner className="h-4 w-4 mr-2" />
                Resetting...
              </>
            ) : (
              "Reset Password"
            )}
          </Button>

          <div className={cn("text-center text-xs", authMuted)}>
            Didn&apos;t receive the code?{" "}
            <button
              type="button"
              onClick={() => onResend()}
              className="text-primary hover:underline font-medium"
            >
              Resend
            </button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
