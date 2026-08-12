"use client";

import React, { createContext, useContext, useEffect, useState } from "react";

type Theme = "light" | "dark";

interface ThemeContextType {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // Read initial theme from document class (set by blocking script)
  const getInitialTheme = (): Theme => {
    if (typeof window === 'undefined') return 'dark';
    return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
  };

  const [theme, setThemeState] = useState<Theme>(getInitialTheme);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    // Sync with what the blocking script set
    const currentTheme = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
    setThemeState(currentTheme);
  }, []);

  useEffect(() => {
    if (mounted) {
      // Save to localStorage
      localStorage.setItem("app-theme", theme);

      // Update document root
      const root = document.documentElement;
      root.classList.remove("light", "dark");
      root.classList.add(theme);

      // Set CSS variables
      if (theme === "dark") {
        root.style.setProperty("--bg-primary", "#1a1a1a"); // Darker for sidebar/chat/header
        root.style.setProperty("--bg-secondary", "#242424"); // Tab bar (perfect, keep this)
        root.style.setProperty("--bg-tertiary", "#2a2a2a"); // Canvas background - lighter gray
        root.style.setProperty("--border-color", "#3e3e42");
        root.style.setProperty("--text-primary", "#e0e0e0");
        root.style.setProperty("--text-secondary", "#a0a0a0");
        root.style.setProperty("--text-tertiary", "#ffffff");
      } else {
        root.style.setProperty("--bg-primary", "#ffffff");
        root.style.setProperty("--bg-secondary", "#f9f9f9"); // Lighter cards/sections
        root.style.setProperty("--bg-tertiary", "#fafafa"); // Hover
        root.style.setProperty("--border-color", "#efefef"); // Lighter borders
        root.style.setProperty("--text-primary", "#1f1f1f"); // Darker black
        root.style.setProperty("--text-secondary", "#737373"); // Darker gray
        root.style.setProperty("--text-tertiary", "#000000");
      }
    }
  }, [theme, mounted]);

  const toggleTheme = () => {
    setThemeState((prev) => (prev === "dark" ? "light" : "dark"));
  };

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme);
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    // Return default values instead of throwing during SSR
    return {
      theme: "dark" as Theme,
      toggleTheme: () => {},
      setTheme: () => {},
    };
  }
  return context;
}
