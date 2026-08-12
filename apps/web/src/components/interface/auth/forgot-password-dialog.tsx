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
import { KeyRound } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import {
  authField,
  authHeadline,
  authLabel,
  authModalContent,
  authMuted,
} from "./auth-surface";

interface ForgotPasswordDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (email: string) => void;
  onShowSignIn: () => void;
  isSubmitting?: boolean;
}

export function ForgotPasswordDialog({
  open,
  onOpenChange,
  onSubmit,
  onShowSignIn,
  isSubmitting = false,
}: ForgotPasswordDialogProps) {
  const [email, setEmail] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (email) {
      onSubmit(email);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={authModalContent}>
        <DialogHeader>
          <div className="flex items-center gap-3 mb-2">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-primary to-primary-strong flex items-center justify-center">
              <KeyRound className="h-5 w-5 text-white" />
            </div>
            <div>
              <DialogTitle className={cn("text-sm font-semibold", authHeadline)}>
                Forgot Password
              </DialogTitle>
              <DialogDescription className={cn("text-xs", authMuted)}>
                We&apos;ll send you a code to reset your password.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 mt-4">
          <div className="grid gap-2">
            <Label className={cn("text-xs", authLabel)}>Email</Label>
            <Input
              type="email"
              placeholder="Enter your email address"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={cn("h-10 text-sm focus:border-primary focus:ring-primary/20", authField)}
            />
          </div>

          <Button
            type="submit"
            disabled={isSubmitting || !email}
            className="w-full bg-primary hover:bg-primary-hover text-primary-foreground text-sm shadow-sm h-10 disabled:opacity-50"
          >
            {isSubmitting ? (
              <>
                <Spinner className="h-4 w-4 mr-2" />
                Sending...
              </>
            ) : (
              "Send Reset Code"
            )}
          </Button>

          <div className={cn("text-center text-xs", authMuted)}>
            Remember your password?{" "}
            <button
              type="button"
              onClick={() => {
                onOpenChange(false);
                onShowSignIn();
              }}
              className="text-primary hover:underline font-medium"
            >
              Sign in
            </button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
