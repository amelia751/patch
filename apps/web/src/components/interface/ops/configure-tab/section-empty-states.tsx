"use client";

import { Button } from "@/components/ui/button";
import { Cloud, CloudOff, Key, FolderPlus, Fingerprint, Vault } from "lucide-react";
import { useRouter } from "next/navigation";

interface ChooseCloudProviderEmptyStateProps {
  onChooseProvider: () => void;
}

export function ChooseCloudProviderEmptyState({ onChooseProvider }: ChooseCloudProviderEmptyStateProps) {
  return (
    <div className="h-full flex items-center justify-center bg-[var(--bg-primary)] px-6">
      <div className="max-w-md text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-[var(--bg-tertiary)]">
          <Cloud className="h-5 w-5 text-[var(--text-secondary)]" />
        </div>
        <h2 className="mb-2 text-sm font-semibold text-[var(--text-primary)]">Choose your cloud provider</h2>
        <p className="mb-6 text-xs text-[var(--text-secondary)] leading-relaxed">
          Pick where you want us to deploy for this project, then you can connect your account.
        </p>
        <Button
          size="sm"
          className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
          onClick={onChooseProvider}
        >
          Choose provider
        </Button>
      </div>
    </div>
  );
}

export function ConnectionEmptyState() {
  const router = useRouter();

  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center max-w-md px-4">
        <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
          <CloudOff className="h-5 w-5 text-[var(--text-secondary)]" />
        </div>
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
          No cloud connection
        </h2>
        <p className="text-xs text-[var(--text-secondary)] mb-6 leading-relaxed">
          Select a project to configure your cloud provider connection and manage infrastructure settings.
        </p>
        <Button
          size="sm"
          onClick={() => router.push("/")}
          className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
        >
          <FolderPlus className="h-3 w-3 mr-1" />
          Select Project
        </Button>
      </div>
    </div>
  );
}

export function SecretsEmptyState() {
  const router = useRouter();

  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center max-w-md px-4">
        <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
          <Key className="h-5 w-5 text-[var(--text-secondary)]" />
        </div>
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
          No secrets configured
        </h2>
        <p className="text-xs text-[var(--text-secondary)] mb-6 leading-relaxed">
          Select a project to manage secrets and configure sensitive data for your backend services.
        </p>
        <Button
          size="sm"
          onClick={() => router.push("/")}
          className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
        >
          <FolderPlus className="h-3 w-3 mr-1" />
          Select Project
        </Button>
      </div>
    </div>
  );
}

export function IdentityEmptyState() {
  const router = useRouter();

  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center max-w-md px-4">
        <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
          <Fingerprint className="h-5 w-5 text-[var(--text-secondary)]" />
        </div>
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
          No agent identity
        </h2>
        <p className="text-xs text-[var(--text-secondary)] mb-6 leading-relaxed">
          Select a project to register SPIFFE principals. Agents authenticate as themselves — no API key.
        </p>
        <Button
          size="sm"
          onClick={() => router.push("/")}
          className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
        >
          <FolderPlus className="h-3 w-3 mr-1" />
          Select Project
        </Button>
      </div>
    </div>
  );
}

export function AuthManagerEmptyState() {
  const router = useRouter();

  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center max-w-md px-4">
        <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
          <Vault className="h-5 w-5 text-[var(--text-secondary)]" />
        </div>
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
          No vault providers
        </h2>
        <p className="text-xs text-[var(--text-secondary)] mb-6 leading-relaxed">
          Select a project to register auth-manager providers. Agents request a name; the vault attaches the secret.
        </p>
        <Button
          size="sm"
          onClick={() => router.push("/")}
          className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
        >
          <FolderPlus className="h-3 w-3 mr-1" />
          Select Project
        </Button>
      </div>
    </div>
  );
}
