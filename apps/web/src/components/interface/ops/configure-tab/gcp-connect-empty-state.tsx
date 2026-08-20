"use client";

import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Cable } from "lucide-react";
import {
  GCPConnectMethodDialog,
} from "./gcp-connect-method-dialog";
import type { SecretRepoOption } from "@/components/interface/secret-managers";
import type { WorkspaceRef } from "./secrets-tab";

const GCP_ENV_OPTIONS = [
  { value: "development", label: "Development" },
  { value: "staging", label: "Staging" },
  { value: "production", label: "Production" },
];

interface GCPConnectEmptyStateProps {
  onConnect?: () => void;
  onChooseAnotherCloudProvider?: () => void;
  userId?: string;
  projectId?: string;
  workspaces?: WorkspaceRef[];
  repoFullName?: string | null;
  repos?: SecretRepoOption[];
  openCredentialModalRequest?: boolean;
  onOpenCredentialModalConsumed?: () => void;
}

export function GCPConnectEmptyState({
  onConnect,
  onChooseAnotherCloudProvider,
  userId = "default",
  projectId,
  workspaces = [],
  repoFullName = null,
  repos = [],
  openCredentialModalRequest = false,
  onOpenCredentialModalConsumed,
}: GCPConnectEmptyStateProps) {
  const [showGcpConnectDialog, setShowGcpConnectDialog] = useState(false);
  const [environment, setEnvironment] = useState("development");

  const consumeCredentialModalRef = useRef(onOpenCredentialModalConsumed);
  consumeCredentialModalRef.current = onOpenCredentialModalConsumed;
  useEffect(() => {
    if (!openCredentialModalRequest) return;
    setShowGcpConnectDialog(true);
    consumeCredentialModalRef.current?.();
  }, [openCredentialModalRequest]);

  return (
    <>
      <div className="h-full flex items-center justify-center bg-[var(--bg-primary)]">
        <div className="text-center max-w-md">
          <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
            <img
              src="/google-cloud.svg"
              alt="Google Cloud"
              className="h-6 w-6"
            />
          </div>
          <h2 className="text-lg font-medium text-[var(--text-primary)] mb-2">
            Connect your GCP project
          </h2>
          <p className="text-sm text-[var(--text-secondary)] mb-6">
            Connect Google Cloud Platform to deploy and manage your infrastructure
          </p>
          <div className="flex w-full max-w-xs flex-col items-center justify-center gap-2 mx-auto">
            <Button
              onClick={() => setShowGcpConnectDialog(true)}
              className="w-full bg-primary hover:bg-primary/90 text-primary-foreground"
            >
              <Cable className="h-4 w-4 mr-2" />
              Connect GCP project
            </Button>
            {onChooseAnotherCloudProvider && (
              <Button
                variant="outline"
                onClick={onChooseAnotherCloudProvider}
                className="w-full border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
              >
                Choose Another Cloud Provider
              </Button>
            )}
          </div>
        </div>
      </div>

      <GCPConnectMethodDialog
        open={showGcpConnectDialog}
        onOpenChange={setShowGcpConnectDialog}
        userId={userId}
        environment={environment}
        onEnvironmentChange={setEnvironment}
        environmentOptions={GCP_ENV_OPTIONS}
        environmentHelpText="This tags the connection in Secret Manager for organization."
        onConnectSuccess={() => onConnect?.()}
        projectId={projectId}
        workspaces={workspaces}
        repoFullName={repoFullName}
        repos={repos}
      />
    </>
  );
}
