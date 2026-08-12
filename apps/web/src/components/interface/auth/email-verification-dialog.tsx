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
import { Mail } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import {
  authField,
  authHeadline,
  authLabel,
  authModalContent,
  authMuted,
} from "./auth-surface";

interface EmailVerificationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onVerify: (code: string) => void;
  onResend: () => void;
  email: string;
  isSubmitting?: boolean;
}

export function EmailVerificationDialog({
  open,
  onOpenChange,
  onVerify,
  onResend,
  email,
  isSubmitting = false,
}: EmailVerificationDialogProps) {
  const [code, setCode] = useState(["", "", "", "", "", ""]);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

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

  const handleVerify = (e: React.FormEvent) => {
    e.preventDefault();
    const codeString = code.join("");
    if (codeString.length === 6) {
      onVerify(codeString);
    }
  };

  const codeComplete = code.every((digit) => digit !== "");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={authModalContent}>
        <DialogHeader>
          <div className="flex items-center gap-3 mb-2">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-primary to-primary-strong flex items-center justify-center">
              <Mail className="h-5 w-5 text-white" />
            </div>
            <div>
              <DialogTitle className={cn("text-sm font-semibold", authHeadline)}>
                Verify Your Email
              </DialogTitle>
              <DialogDescription className={cn("text-xs", authMuted)}>
                We sent a verification code to {email}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <form onSubmit={handleVerify} className="space-y-4 mt-4">
          <div className="grid gap-2">
            <Label className={cn("text-xs", authLabel)}>Verification Code</Label>
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

          <Button
            type="submit"
            disabled={isSubmitting || !codeComplete}
            className="w-full bg-primary hover:bg-primary-hover text-primary-foreground text-sm shadow-sm h-10 disabled:opacity-50"
          >
            {isSubmitting ? (
              <>
                <Spinner className="h-4 w-4 mr-2" />
                Verifying...
              </>
            ) : (
              "Verify Email"
            )}
          </Button>

          <div className={cn("text-center text-xs", authMuted)}>
            Didn&apos;t receive the code?{" "}
            <button type="button" onClick={onResend} className="text-primary hover:underline font-medium">
              Resend
            </button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
