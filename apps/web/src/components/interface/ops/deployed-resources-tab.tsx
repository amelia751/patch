"use client";

import { useState, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { ExternalLink } from "lucide-react";
import { useTheme } from "@/lib/theme-context";
import { cn } from "@/lib/utils";

interface DeployedResourcesTabProps {
  currentEnv: any;
  environment: string;
}

export function DeployedResourcesTab({ currentEnv, environment }: DeployedResourcesTabProps) {
  const { theme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (currentEnv.status !== "deployed") {
    return (
      <div className="h-full flex items-center justify-center bg-[var(--bg-primary)]">
        <div className="text-center">
          <p className="text-sm text-[var(--text-secondary)]">
            No resources deployed in {environment} environment
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-[var(--bg-primary)]">
      <div className="max-w-5xl mx-auto p-6 space-y-6">
        {/* Environment Info */}
        <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-[var(--text-primary)] capitalize">{environment} Environment</h3>
            <span className={cn(
              "text-[10px] px-2 py-0.5 rounded-full font-medium",
              mounted && theme === "dark" && "bg-transparent text-[#10b981] border border-[#10b981]/30",
              mounted && theme === "light" && "bg-[#10b981] text-white"
            )}>
              Deployed
            </span>
          </div>

          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-4 text-xs">
              <div>
                <p className="text-[var(--text-secondary)] mb-1">Last Deployed</p>
                <p className="text-[var(--text-primary)] font-medium">
                  {new Date(currentEnv.last_deployed).toLocaleDateString()} at {new Date(currentEnv.last_deployed).toLocaleTimeString()}
                </p>
              </div>
              <div>
                <p className="text-[var(--text-secondary)] mb-1">Deployed By</p>
                <p className="text-[var(--text-primary)] font-medium">{currentEnv.deployed_by}</p>
              </div>
            </div>

            <div className="pt-3 border-t border-[var(--border-color)]">
              <p className="text-[var(--text-secondary)] text-xs mb-2">Endpoint URL</p>
              <a
                href={currentEnv.endpoint_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 text-xs text-primary hover:underline font-mono"
              >
                {currentEnv.endpoint_url}
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>

            <div className="pt-3 border-t border-[var(--border-color)]">
              <p className="text-[var(--text-secondary)] text-xs mb-2">Resources</p>
              <div className="flex gap-3 flex-wrap">
                <span className="text-xs bg-[var(--bg-tertiary)] px-2 py-1 rounded border border-[var(--border-color)] text-[var(--text-primary)]">
                  {currentEnv.resources.lambda_functions} Lambda Functions
                </span>
                <span className="text-xs bg-[var(--bg-tertiary)] px-2 py-1 rounded border border-[var(--border-color)] text-[var(--text-primary)]">
                  {currentEnv.resources.databases} Database
                </span>
                <span className="text-xs bg-[var(--bg-tertiary)] px-2 py-1 rounded border border-[var(--border-color)] text-[var(--text-primary)]">
                  {currentEnv.resources.s3_buckets} S3 Buckets
                </span>
              </div>
            </div>

            <div className="pt-3 border-t border-[var(--border-color)]">
              <div className="flex items-center justify-between">
                <p className="text-[var(--text-secondary)] text-xs">Estimated Monthly Cost</p>
                <p className="text-sm font-semibold text-[var(--text-primary)]">${currentEnv.monthly_cost.toFixed(2)}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
