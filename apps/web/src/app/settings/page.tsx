"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { Key } from "lucide-react";
import { ByokSettings } from "@/components/interface/settings";

const SETTINGS_SECTIONS = [
  { id: "byok" as const, label: "BYOK", icon: Key },
];

export default function SettingsPage() {
  const [activeSection, setActiveSection] = useState<(typeof SETTINGS_SECTIONS)[number]["id"]>("byok");

  return (
    <div className="flex h-full min-h-0 overflow-hidden bg-[var(--bg-secondary)] transition-colors">
      <aside className="w-52 flex-shrink-0 border-r border-[var(--border-color)] bg-[var(--bg-primary)] px-3 py-4">
        <h1 className="px-3 text-xs font-semibold text-[var(--text-primary)] mb-3">
          Settings
        </h1>
        <nav className="space-y-1">
          {SETTINGS_SECTIONS.map((section) => (
            <button
              key={section.id}
              type="button"
              onClick={() => setActiveSection(section.id)}
              className={cn(
                "w-full flex items-center gap-2.5 px-3 py-2 text-xs rounded-lg transition-all duration-200",
                activeSection === section.id
                  ? "bg-primary text-white shadow-sm"
                  : "text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
              )}
            >
              <section.icon className="h-3.5 w-3.5 flex-shrink-0" />
              {section.label}
            </button>
          ))}
        </nav>
      </aside>

      <div className="flex-1 min-w-0 overflow-y-auto">
        {activeSection === "byok" && <ByokSettings />}
      </div>
    </div>
  );
}
