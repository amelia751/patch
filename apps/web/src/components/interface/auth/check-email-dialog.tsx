"use client";

import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Mail } from "lucide-react";
import {
  authHeadline,
  authModalContent,
  authMuted,
} from "./auth-surface";

interface CheckEmailDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  email: string;
  onShowSignIn: () => void;
  title?: string;
  description?: string;
}

export function CheckEmailDialog({
  open,
  onOpenChange,
  email,
  onShowSignIn,
  title = "Check your email",
  description = "If an account exists for that address, we sent a reset link. Open it to choose a new password.",
}: CheckEmailDialogProps) {
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
                {title}
              </DialogTitle>
              <DialogDescription className={cn("text-xs", authMuted)}>
                {description}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>
        {email ? (
          <p className={cn("text-sm mt-2", authHeadline)}>
            Sent to <span className="font-medium">{email}</span>
          </p>
        ) : null}
        <Button
          type="button"
          onClick={() => {
            onOpenChange(false);
            onShowSignIn();
          }}
          className="w-full bg-primary hover:bg-primary-hover text-primary-foreground text-sm shadow-sm h-10 mt-4"
        >
          Back to sign in
        </Button>
      </DialogContent>
    </Dialog>
  );
}
