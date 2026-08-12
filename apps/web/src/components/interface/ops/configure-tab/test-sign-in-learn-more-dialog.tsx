"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { LOGIN_ASSET } from "./google-test-connect-dialog";

const LEARN_SLIDES: {
  title: string;
  body: string;
  image: { src: string; alt: string };
}[] = [
  {
    title: "Why not fake or bypass login?",
    body: "Shortcuts age badly. Mock JWTs or turning auth off might work today, then your middleware, cookies, or refresh flow changes and tests quietly stop matching production.",
    image: { src: LOGIN_ASSET("forgot-password.png"), alt: "Forgot password" },
  },
  {
    title: "What about a real browser?",
    body: "Automating Chrome (e.g. Playwright) can record a true session, but sign-in often hits CAPTCHAs, MFA, or UI churn. Useful sometimes—not what we want for every routine run.",
    image: { src: LOGIN_ASSET("secure-platform.png"), alt: "Secure platform" },
  },
  {
    title: "What JetRun does",
    body: "You sign in with Google the way your app already does. We store the session your backend issues and attach it in sandbox runs—a stable, logged-in tester inside your app.",
    image: { src: LOGIN_ASSET("secure-browser.png"), alt: "Secure browser" },
  },
  {
    title: "Use a test account",
    body: "Connect a dedicated staging or QA user, not a personal or customer account. Same real login path, safer data and clearer boundaries.",
    image: { src: LOGIN_ASSET("successful-login.png"), alt: "Successful login" },
  },
];

const learnSlideCount = LEARN_SLIDES.length;

export interface TestSignInLearnMoreDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function TestSignInLearnMoreDialog({ open, onOpenChange }: TestSignInLearnMoreDialogProps) {
  const [learnSlide, setLearnSlide] = useState(0);

  useEffect(() => {
    if (open) setLearnSlide(0);
  }, [open]);

  const learnAtEnd = learnSlide >= learnSlideCount - 1;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) setLearnSlide(0);
      }}
    >
      <DialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)] max-w-md gap-0 p-0 overflow-hidden">
        <DialogHeader className="px-5 pt-5 pb-3 border-b border-[var(--border-color)]">
          <DialogTitle className="text-sm font-semibold text-[var(--text-primary)] text-left">
            Why test sign-in works this way
          </DialogTitle>
          <p className="text-[10px] text-[var(--text-secondary)] text-left font-normal pt-1">
            {learnSlide + 1} / {learnSlideCount}
          </p>
        </DialogHeader>

        <div className="px-5 py-5 flex flex-col justify-center gap-3" aria-live="polite">
          <div className="relative mx-auto w-full max-w-[220px] aspect-[5/4] overflow-hidden shrink-0">
            <Image
              src={LEARN_SLIDES[learnSlide].image.src}
              alt={LEARN_SLIDES[learnSlide].image.alt}
              fill
              sizes="220px"
              quality={95}
              className="object-cover object-center"
            />
          </div>
          <h3 className="text-sm font-medium text-[var(--text-primary)]">
            {LEARN_SLIDES[learnSlide].title}
          </h3>
          <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
            {LEARN_SLIDES[learnSlide].body}
          </p>
        </div>

        <div className="flex items-center justify-between gap-2 px-5 py-3 border-t border-[var(--border-color)] bg-[var(--bg-secondary)]/50">
          <div className="flex gap-1.5">
            {LEARN_SLIDES.map((_, i) => (
              <button
                key={i}
                type="button"
                aria-label={`Go to slide ${i + 1}`}
                onClick={() => setLearnSlide(i)}
                className={cn(
                  "h-1.5 rounded-full transition-all",
                  i === learnSlide
                    ? "w-5 bg-primary"
                    : "w-1.5 bg-[var(--border-color)] hover:bg-[var(--text-secondary)]/40"
                )}
              />
            ))}
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={learnSlide === 0}
              onClick={() => setLearnSlide((s) => Math.max(0, s - 1))}
              className="h-8 w-8 shrink-0 p-0 border-[var(--border-color)] bg-[var(--bg-primary)] text-[var(--text-primary)] shadow-sm hover:!bg-[var(--bg-tertiary)] hover:!text-[var(--text-primary)] disabled:!bg-transparent disabled:!text-[var(--text-secondary)] disabled:hover:!bg-transparent"
              aria-label="Previous slide"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            {learnAtEnd ? (
              <Button
                type="button"
                size="sm"
                onClick={() => onOpenChange(false)}
                className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
              >
                Done
              </Button>
            ) : (
              <Button
                type="button"
                size="sm"
                onClick={() => setLearnSlide((s) => Math.min(learnSlideCount - 1, s + 1))}
                className="h-8 text-xs inline-flex items-center gap-0.5 bg-primary hover:bg-primary/90 text-primary-foreground"
              >
                Next
                <ChevronRight className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
