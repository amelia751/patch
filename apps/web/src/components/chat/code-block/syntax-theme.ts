"use client";

import { useMemo } from "react";
import { useTheme } from "@/lib/theme-context";
import { vscDarkPlus, vs } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { CSSProperties } from "react";

/**
 * Shared monospace font stack (matches system IDE fonts).
 */
export const MONO_FONT =
  "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace";

/**
 * Normalise a Prism theme so it never uses the `background` shorthand.
 * React warns when shorthand (`background`) and longhand (`backgroundColor`)
 * are both present on the same element across re-renders.
 */
function normalizeTheme(theme: Record<string, CSSProperties>) {
  const patched: Record<string, CSSProperties> = {};
  for (const key of Object.keys(theme)) {
    const styles = { ...theme[key] };
    if ("background" in styles) {
      // Move shorthand → longhand so it never conflicts with backgroundColor
      if (!styles.backgroundColor) {
        styles.backgroundColor = styles.background as string;
      }
      delete styles.background;
    }
    patched[key] = styles;
  }
  return patched;
}

/**
 * Returns the correct Prism theme + overrides for current light/dark mode.
 */
export function useSyntaxTheme() {
  const { theme } = useTheme();
  const isDark = theme === "dark";

  const prismTheme = useMemo(
    () => normalizeTheme(isDark ? vscDarkPlus : vs),
    [isDark]
  );

  /** Overrides for the <pre> element */
  const preStyle: CSSProperties = {
    margin: 0,
    padding: "12px",
    fontSize: "11px",
    lineHeight: "1.5",
    backgroundColor: "var(--bg-secondary)",
    borderRadius: 0,
    fontFamily: MONO_FONT,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    overflow: "hidden",
  };

  /** Overrides for the <code> element */
  const codeStyle: CSSProperties = {
    fontFamily: MONO_FONT,
    fontSize: "11px",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word" as const,
  };

  return { prismTheme, preStyle, codeStyle, isDark };
}
