"use client";

import { ThemeProvider } from "@/lib/theme-context";
import { AuthProvider } from "@/lib/auth-context";
import { ProjectProvider } from "@/lib/project-context";
import { ArchitectureProvider } from "@/lib/architecture-context";
import { ConsoleEventsProvider } from "@/hooks/useConsoleEvents";
import { AppLayout } from "./app-layout";
import { TestGoogleSessionProvider } from "@/lib/test-google-session-context";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ProjectProvider>
          <ArchitectureProvider>
            <ConsoleEventsProvider>
              <TestGoogleSessionProvider>
                <AppLayout>{children}</AppLayout>
              </TestGoogleSessionProvider>
            </ConsoleEventsProvider>
          </ArchitectureProvider>
        </ProjectProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
