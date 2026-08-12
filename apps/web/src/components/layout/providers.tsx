"use client";

import { ThemeProvider } from "@/lib/theme-context";
import { AuthProvider } from "@/lib/auth-context";
import { ProjectProvider } from "@/lib/project-context";
import { ArchitectureProvider } from "@/lib/architecture-context";
import { DemoProvider } from "@/lib/demo-context";
import { AppLayout } from "./app-layout";
import { TestGoogleSessionProvider } from "@/lib/test-google-session-context";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ProjectProvider>
          <ArchitectureProvider>
            <DemoProvider>
              <TestGoogleSessionProvider>
                <AppLayout>{children}</AppLayout>
              </TestGoogleSessionProvider>
            </DemoProvider>
          </ArchitectureProvider>
        </ProjectProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
