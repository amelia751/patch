import type { Metadata } from "next";
import { Geist, Geist_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/layout/providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "PatchAPI — Dependabot for APIs",
  description:
    "When an external API changes, PatchAPI finds the affected code, verifies a migration, and opens a pull request.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                function getTheme() {
                  const savedTheme = localStorage.getItem('app-theme');
                  if (savedTheme) return savedTheme;
                  // Default to dark mode
                  return 'dark';
                }

                const theme = getTheme();
                const root = document.documentElement;
                root.classList.add(theme);

                if (theme === 'dark') {
                  root.style.setProperty('--bg-primary', '#1a1a1a');
                  root.style.setProperty('--bg-secondary', '#242424');
                  root.style.setProperty('--bg-tertiary', '#2a2a2a');
                  root.style.setProperty('--border-color', '#3e3e42');
                  root.style.setProperty('--text-primary', '#e0e0e0');
                  root.style.setProperty('--text-secondary', '#a0a0a0');
                  root.style.setProperty('--text-tertiary', '#ffffff');
                } else {
                  root.style.setProperty('--bg-primary', '#ffffff');
                  root.style.setProperty('--bg-secondary', '#f5f5f5');
                  root.style.setProperty('--bg-tertiary', '#e5e5e5');
                  root.style.setProperty('--border-color', '#e0e0e0');
                  root.style.setProperty('--text-primary', '#333333');
                  root.style.setProperty('--text-secondary', '#666666');
                  root.style.setProperty('--text-tertiary', '#000000');
                }
              })();
            `,
          }}
        />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${spaceGrotesk.variable} antialiased`}
      >
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
