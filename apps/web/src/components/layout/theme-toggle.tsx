"use client";

import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * Light/dark toggle.
 *
 * There is deliberately no React state here. The `dark` class on `<html>` is
 * the single source of truth — set before first paint by the inline script in
 * the root layout — and which icon shows is decided by CSS from that same
 * class. Mirroring the class into state would reintroduce both the flash of
 * the wrong theme and a hydration mismatch when the stored choice is `light`.
 */
export function ThemeToggle() {
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label="Toggle light and dark theme"
      onClick={() => {
        const root = document.documentElement;
        const next = root.classList.contains("dark") ? "light" : "dark";
        root.classList.toggle("dark", next === "dark");
        root.classList.toggle("light", next === "light");
        try {
          window.localStorage.setItem("patch-theme", next);
        } catch {
          // A blocked storage API costs the preference across reloads, not the
          // toggle itself.
        }
      }}
    >
      <Sun className="size-4 dark:hidden" />
      <Moon className="hidden size-4 dark:block" />
    </Button>
  );
}
