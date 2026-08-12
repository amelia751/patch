"use client";

import React from "react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface EnvironmentSelectorProps {
  environments: string[];
  currentEnvironment: string;
  onEnvironmentChange: (environment: string) => void;
}

const getEnvironmentColorClass = (env: string) => {
  // Using theme-aware colors for better light/dark mode support
  switch (env) {
    case "dev":
      return "data-[state=active]:bg-slate-500/20 data-[state=active]:text-slate-600 dark:data-[state=active]:text-slate-400";
    case "staging":
      return "data-[state=active]:bg-amber-500/20 data-[state=active]:text-amber-600 dark:data-[state=active]:text-amber-400";
    case "prod":
      return "data-[state=active]:bg-emerald-500/20 data-[state=active]:text-emerald-600 dark:data-[state=active]:text-emerald-400";
    default:
      return "data-[state=active]:bg-[var(--bg-primary)] data-[state=active]:text-[var(--text-tertiary)]";
  }
};

export function EnvironmentSelector({ environments, currentEnvironment, onEnvironmentChange }: EnvironmentSelectorProps) {
  return (
    <div className="absolute top-4 right-4 z-10">
      <Tabs value={currentEnvironment} onValueChange={onEnvironmentChange}>
        <TabsList className="bg-[var(--bg-secondary)] border border-[var(--border-color)] p-1 transition-colors">
          {environments.map((env) => (
            <TabsTrigger
              key={env}
              value={env}
              className={`px-3 py-1.5 text-[11px] font-medium rounded-md transition-all text-[var(--text-secondary)] hover:text-[var(--text-primary)] data-[state=active]:shadow ${getEnvironmentColorClass(env)}`}
            >
              {env}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
    </div>
  );
}

