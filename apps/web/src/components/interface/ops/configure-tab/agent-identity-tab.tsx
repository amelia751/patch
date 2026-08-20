"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Cable,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Copy,
  ExternalLink,
  Fingerprint,
  Trash2,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Spinner } from "@/components/ui/spinner";

type Binding = {
  role: string;
  label: string;
  validated: boolean;
};

type FleetAgent = {
  id: string;
  name: string;
  job: string;
  principal: string;
  bindings: Binding[];
};

const FLEET: Omit<FleetAgent, "bindings">[] = [
  {
    id: "change",
    name: "Change Intelligence",
    job: "Reads provider notices on Vertex",
    principal:
      "principal://agents.global.org-patchapi.system.id.goog/resources/aiplatform/projects/913371146929/locations/us-central1/reasoningEngines/change",
  },
  {
    id: "impact",
    name: "Impact",
    job: "Reads Memory Bank for the imported repo",
    principal:
      "principal://agents.global.org-patchapi.system.id.goog/resources/aiplatform/projects/913371146929/locations/us-central1/reasoningEngines/impact",
  },
  {
    id: "patch",
    name: "Patch",
    job: "Reasons on Vertex; writes only inside a sandbox",
    principal:
      "principal://agents.global.org-patchapi.system.id.goog/resources/aiplatform/projects/913371146929/locations/us-central1/reasoningEngines/patch",
  },
  {
    id: "verification",
    name: "Verification",
    job: "Grades a clean sandbox on Vertex",
    principal:
      "principal://agents.global.org-patchapi.system.id.goog/resources/aiplatform/projects/913371146929/locations/us-central1/reasoningEngines/verification",
  },
];

const BINDINGS_FOR: Record<string, { role: string; label: string }[]> = {
  change: [{ role: "roles/aiplatform.user", label: "Vertex AI User" }],
  impact: [
    { role: "roles/aiplatform.user", label: "Vertex AI User" },
    { role: "roles/aiplatform.memoryUser", label: "Vertex AI Memory User" },
  ],
  patch: [{ role: "roles/aiplatform.user", label: "Vertex AI User" }],
  verification: [{ role: "roles/aiplatform.user", label: "Vertex AI User" }],
};

const IAM_URL =
  "https://console.cloud.google.com/iam-admin/iam?project=patch-505223";
const AGENT_IDENTITY_URL =
  "https://console.cloud.google.com/vertex-ai?project=patch-505223";

function seedAgents(validated: boolean): FleetAgent[] {
  return FLEET.map((agent) => ({
    ...agent,
    bindings: BINDINGS_FOR[agent.id].map((b, i) => ({
      ...b,
      validated: validated && !(agent.id === "impact" && i === 1),
    })),
  }));
}

function Copyable({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-start gap-1.5 bg-[var(--bg-primary)] border border-[var(--border-color)] rounded-md px-2.5 py-1.5">
      <span className="flex-1 text-[10px] font-mono text-[var(--text-primary)] break-all select-all">
        {value}
      </span>
      <button
        type="button"
        onClick={() => {
          void navigator.clipboard.writeText(value);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        }}
        className="shrink-0 p-0.5 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        title="Copy"
      >
        {copied ? <Check className="h-3 w-3 text-[#10b981]" /> : <Copy className="h-3 w-3" />}
      </button>
    </div>
  );
}

function ConsoleChip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-md border border-primary/35 bg-primary/10 px-1.5 py-0.5 text-[9px] font-semibold text-[var(--text-primary)]">
      {children}
    </span>
  );
}

export function AgentIdentityTab() {
  const [connected, setConnected] = useState(false);
  const [connectOpen, setConnectOpen] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [agents, setAgents] = useState<FleetAgent[]>(() => seedAgents(false));
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [validating, setValidating] = useState<string | null>(null);
  const [detachOpen, setDetachOpen] = useState(false);
  const [detachConfirm, setDetachConfirm] = useState("");

  const bindingStats = agents.reduce(
    (acc, a) => {
      acc.total += a.bindings.length;
      acc.ok += a.bindings.filter((b) => b.validated).length;
      return acc;
    },
    { ok: 0, total: 0 },
  );
  const allValid = bindingStats.ok === bindingStats.total && bindingStats.total > 0;

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const mockConnect = () => {
    setConnecting(true);
    window.setTimeout(() => {
      setAgents(seedAgents(true));
      setConnected(true);
      setConnecting(false);
      setConnectOpen(false);
    }, 700);
  };

  const mockValidate = (agentId: string, role: string) => {
    const key = `${agentId}:${role}`;
    setValidating(key);
    window.setTimeout(() => {
      setAgents((prev) =>
        prev.map((a) =>
          a.id !== agentId
            ? a
            : {
                ...a,
                bindings: a.bindings.map((b) => (b.role === role ? { ...b, validated: true } : b)),
              },
        ),
      );
      setValidating(null);
    }, 500);
  };

  const disconnect = () => {
    setConnected(false);
    setAgents(seedAgents(false));
    setDetachOpen(false);
    setDetachConfirm("");
    setExpanded(new Set());
  };

  return (
    <>
      <Dialog open={connectOpen} onOpenChange={setConnectOpen}>
        <DialogContent className="max-w-lg bg-[var(--bg-primary)] border-[var(--border-color)] flex flex-col max-h-[min(90dvh,40rem)] gap-0 overflow-hidden p-0 sm:max-w-lg">
          <div className="shrink-0 px-6 pt-6 pb-4 border-b border-[var(--border-color)]">
            <DialogHeader className="space-y-0 text-left">
              <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">
                Connect Agent Identity
              </DialogTitle>
              <DialogDescription className="text-xs text-[var(--text-secondary)] pt-2">
                The four PatchAPI agents already exist. Bind their principals on this GCP project.
                No JSON key. Same idea as WIF: you grant IAM, we validate.
              </DialogDescription>
            </DialogHeader>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto px-6 py-4 space-y-4">
            <div className="border border-[var(--border-color)] rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-xs font-medium text-[var(--text-primary)]">
                  Step 1: Copy each agent principal
                </h3>
                <a
                  href={AGENT_IDENTITY_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] text-primary hover:underline inline-flex items-center gap-1"
                >
                  Open Vertex AI
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
                These SPIFFE ids are issued by Gemini Enterprise Agent Platform. You do not create
                them here.
              </p>
              <div className="space-y-2">
                {FLEET.map((agent) => (
                  <div key={agent.id} className="space-y-1">
                    <p className="text-[10px] font-medium text-[var(--text-primary)]">{agent.name}</p>
                    <Copyable value={agent.principal} />
                  </div>
                ))}
              </div>
            </div>

            <div className="border border-[var(--border-color)] rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-xs font-medium text-[var(--text-primary)]">
                  Step 2: Grant IAM on this project
                </h3>
                <a
                  href={IAM_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] text-primary hover:underline inline-flex items-center gap-1"
                >
                  Open IAM
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
              <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3">
                <ol className="text-[10px] text-[var(--text-primary)] space-y-2 list-decimal list-inside">
                  <li>
                    Open <ConsoleChip>IAM</ConsoleChip> → <ConsoleChip>Grant access</ConsoleChip>
                  </li>
                  <li>Paste one principal as the new principal</li>
                  <li>
                    Assign <span className="font-mono">Vertex AI User</span>{" "}
                    <span className="font-mono text-[var(--text-secondary)]">(roles/aiplatform.user)</span>
                  </li>
                  <li>
                    For Impact only, also assign{" "}
                    <span className="font-mono">Vertex AI Memory User</span>
                  </li>
                  <li>
                    Save. Repeat for the other three agents. No API key, no JSON download.
                  </li>
                </ol>
              </div>
            </div>

            <div className="border border-[var(--border-color)] rounded-lg p-4 space-y-2">
              <h3 className="text-xs font-medium text-[var(--text-primary)]">
                Step 3: Validate
              </h3>
              <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
                PatchAPI calls Vertex as each principal. If IAM is correct, the agent is attested.
                Mock: Connect marks the fleet connected and re-checks bindings.
              </p>
            </div>
          </div>
          <DialogFooter className="shrink-0 border-t border-[var(--border-color)] px-6 py-4">
            <Button
              variant="outline"
              onClick={() => setConnectOpen(false)}
              className="text-xs border-[var(--border-color)] text-[var(--text-primary)]"
            >
              Cancel
            </Button>
            <Button
              onClick={mockConnect}
              disabled={connecting}
              className="text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
            >
              {connecting ? (
                <>
                  <Spinner className="h-3.5 w-3.5 mr-2" />
                  Validating…
                </>
              ) : (
                <>
                  <Cable className="h-3.5 w-3.5 mr-1.5" />
                  Connect and validate
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="h-full overflow-y-auto bg-[var(--bg-primary)] min-w-0">
        {!connected ? (
          <div className="p-6">
            <div className="flex items-center gap-3 mb-6">
              <Fingerprint className="h-5 w-5 text-[var(--text-primary)]" />
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">Agent Identity</h2>
            </div>
            <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-12 text-center">
              <div className="h-12 w-12 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-4">
                <Fingerprint className="h-5 w-5 text-[var(--text-secondary)]" />
              </div>
              <h3 className="text-sm font-medium text-[var(--text-primary)] mb-2">
                Identity not connected
              </h3>
              <p className="text-xs text-[var(--text-secondary)] mb-4 max-w-sm mx-auto leading-relaxed">
                Change, Impact, Patch, and Verification already have SPIFFE principals. Connect
                them to this GCP project and validate IAM — same pattern as WIF, no key file.
              </p>
              <Button
                onClick={() => setConnectOpen(true)}
                className="bg-primary hover:bg-primary/90 text-primary-foreground"
              >
                <Cable className="h-4 w-4 mr-2" />
                Connect Agent Identity
              </Button>
            </div>
          </div>
        ) : (
          <div className="p-6 space-y-6">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <Fingerprint className="h-5 w-5 text-[var(--text-primary)]" />
                <h2 className="text-sm font-semibold text-[var(--text-primary)]">Agent Identity</h2>
              </div>
            </div>

            <div className="border border-[var(--border-color)] rounded-lg overflow-hidden bg-[var(--bg-secondary)]">
              <div className="p-4 bg-[var(--bg-primary)] flex items-center gap-3">
                {allValid ? (
                  <CheckCircle2 className="h-4 w-4 text-[#10b981] shrink-0" />
                ) : (
                  <XCircle className="h-4 w-4 text-amber-500 shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-[var(--text-primary)]">
                    Fleet principals · patch-505223
                  </p>
                  <p className="text-[10px] text-[var(--text-secondary)] mt-0.5">
                    Gemini 3.5 Flash · global · {bindingStats.ok}/{bindingStats.total} bindings
                    validated
                  </p>
                </div>
              </div>
            </div>

            <div className="space-y-3">
              {agents.map((agent) => {
                const open = expanded.has(agent.id);
                const ok = agent.bindings.every((b) => b.validated);
                return (
                  <div
                    key={agent.id}
                    className="border border-[var(--border-color)] rounded-lg overflow-hidden bg-[var(--bg-secondary)]"
                  >
                    <button
                      type="button"
                      onClick={() => toggle(agent.id)}
                      className="w-full p-4 bg-[var(--bg-primary)] flex items-center gap-3 text-left hover:bg-[var(--bg-tertiary)]/50 transition-colors"
                    >
                      {ok ? (
                        <CheckCircle2 className="h-4 w-4 text-[#10b981] shrink-0" />
                      ) : (
                        <XCircle className="h-4 w-4 text-amber-500 shrink-0" />
                      )}
                      <span className="text-xs font-medium text-[var(--text-primary)] shrink-0">
                        {agent.name}
                      </span>
                      <span className="text-[10px] text-[var(--text-secondary)] truncate flex-1 min-w-0">
                        {agent.job}
                      </span>
                      {open ? (
                        <ChevronUp className="h-4 w-4 text-[var(--text-secondary)] shrink-0" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-[var(--text-secondary)] shrink-0" />
                      )}
                    </button>
                    {open && (
                      <div className="border-t border-[var(--border-color)] p-5 space-y-4">
                        <div>
                          <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)] mb-1.5">
                            Principal
                          </p>
                          <Copyable value={agent.principal} />
                        </div>
                        <div>
                          <div className="flex items-center justify-between mb-3">
                            <h4 className="text-xs font-semibold text-[var(--text-primary)]">
                              Required IAM
                            </h4>
                            <span className="text-[10px] text-[var(--text-secondary)]">
                              {agent.bindings.filter((b) => b.validated).length}/{agent.bindings.length}{" "}
                              validated
                            </span>
                          </div>
                          <div className="space-y-2">
                            {agent.bindings.map((b) => {
                              const key = `${agent.id}:${b.role}`;
                              return (
                                <div
                                  key={b.role}
                                  className="flex items-center justify-between gap-3 p-3 rounded-lg border border-[var(--border-color)] bg-[var(--bg-primary)]"
                                >
                                  <div className="flex items-center gap-2 min-w-0">
                                    {b.validated ? (
                                      <CheckCircle2 className="h-3.5 w-3.5 text-[#10b981] shrink-0" />
                                    ) : (
                                      <XCircle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                                    )}
                                    <div className="min-w-0">
                                      <p className="text-xs font-medium text-[var(--text-primary)]">
                                        {b.label}
                                      </p>
                                      <p className="text-[10px] font-mono text-[var(--text-secondary)]">
                                        {b.role}
                                      </p>
                                    </div>
                                  </div>
                                  {!b.validated && (
                                    <div className="flex items-center gap-1.5 shrink-0">
                                      <Button
                                        size="sm"
                                        variant="outline"
                                        onClick={() => window.open(IAM_URL, "_blank")}
                                        className="text-[10px] h-7 border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                                      >
                                        Grant
                                      </Button>
                                      <Button
                                        size="sm"
                                        variant="outline"
                                        onClick={() => mockValidate(agent.id, b.role)}
                                        disabled={validating === key}
                                        className="text-[10px] h-7 border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                                      >
                                        {validating === key ? (
                                          <Spinner className="h-3 w-3" />
                                        ) : (
                                          "Validate"
                                        )}
                                      </Button>
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {!allValid && (
              <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-3">
                <p className="text-[10px] text-amber-600 dark:text-amber-500">
                  <strong>Warning:</strong> Some principals are missing IAM. Vertex will reject those
                  agents until you grant and validate.
                </p>
              </div>
            )}

            <div className="border-t border-[var(--border-color)] pt-5">
              {!detachOpen ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="text-[10px] h-7 border-red-500/30 text-red-500 hover:bg-red-500/10 hover:text-red-500"
                  onClick={() => {
                    setDetachOpen(true);
                    setDetachConfirm("");
                  }}
                >
                  <Trash2 className="h-3 w-3 mr-1.5" />
                  Disconnect
                </Button>
              ) : (
                <div className="space-y-3 max-w-sm">
                  <p className="text-[10px] text-[var(--text-secondary)]">
                    Type <strong className="text-red-500">DISCONNECT</strong> to confirm. Principals
                    stay issued; only this project binding is dropped.
                  </p>
                  <Input
                    value={detachConfirm}
                    onChange={(e) => setDetachConfirm(e.target.value)}
                    placeholder="Type DISCONNECT"
                    className="h-8 text-xs bg-[var(--bg-primary)] border-red-500/30 text-[var(--text-primary)]"
                  />
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-[10px] h-7 border-[var(--border-color)]"
                      onClick={() => setDetachOpen(false)}
                    >
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      className="text-[10px] h-7 bg-red-500 hover:bg-red-600 text-white"
                      disabled={detachConfirm !== "DISCONNECT"}
                      onClick={disconnect}
                    >
                      Disconnect
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
