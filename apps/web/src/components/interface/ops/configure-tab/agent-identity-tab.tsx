"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Fingerprint, Plus, Shield } from "lucide-react";
import { cn } from "@/lib/utils";

type Grant = "aiplatform.user" | "aiplatform.memoryUser" | "sandbox.allocate";

type PrincipalRow = {
  id: string;
  agent: string;
  role: string;
  principal: string;
  grants: Grant[];
};

const GRANT_OPTIONS: { id: Grant; label: string; hint: string }[] = [
  { id: "aiplatform.user", label: "aiplatform.user", hint: "Vertex accepts this principal. No API key." },
  { id: "aiplatform.memoryUser", label: "aiplatform.memoryUser", hint: "Memory Bank read/write for this agent." },
  { id: "sandbox.allocate", label: "sandbox.allocate", hint: "Claim a sandbox. Still no control-plane key." },
];

const INITIAL: PrincipalRow[] = [
  {
    id: "change",
    agent: "Change Intelligence",
    role: "Detects provider notices",
    principal:
      "principal://agents.global.org-patchapi.system.id.goog/resources/aiplatform/projects/913371146929/locations/us-central1/reasoningEngines/change",
    grants: ["aiplatform.user"],
  },
  {
    id: "impact",
    agent: "Impact",
    role: "Maps a notice onto imported repos",
    principal:
      "principal://agents.global.org-patchapi.system.id.goog/resources/aiplatform/projects/913371146929/locations/us-central1/reasoningEngines/impact",
    grants: ["aiplatform.user", "aiplatform.memoryUser"],
  },
  {
    id: "patch",
    agent: "Patch",
    role: "Edits a sandbox workspace only",
    principal:
      "principal://agents.global.org-patchapi.system.id.goog/resources/aiplatform/projects/913371146929/locations/us-central1/reasoningEngines/patch",
    grants: ["aiplatform.user", "sandbox.allocate"],
  },
  {
    id: "verification",
    agent: "Verification",
    role: "Grades a clean sandbox, not its own work",
    principal:
      "principal://agents.global.org-patchapi.system.id.goog/resources/aiplatform/projects/913371146929/locations/us-central1/reasoningEngines/verification",
    grants: ["aiplatform.user"],
  },
];

function shortPrincipal(spiffe: string): string {
  const tail = spiffe.split("/").pop() ?? spiffe;
  return `…/reasoningEngines/${tail}`;
}

export function AgentIdentityTab() {
  const [rows, setRows] = useState(INITIAL);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [grants, setGrants] = useState<Set<Grant>>(() => new Set(["aiplatform.user"]));

  const resetDialog = () => {
    setName("");
    setGrants(new Set(["aiplatform.user"]));
  };

  const previewId = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "agent";
  const previewPrincipal =
    `principal://agents.global.org-patchapi.system.id.goog/resources/aiplatform/projects/913371146929/locations/us-central1/reasoningEngines/${previewId}`;

  const register = () => {
    const agent = name.trim();
    if (!agent) return;
    const id = `${previewId}-${rows.length + 1}`;
    setRows((prev) => [
      ...prev,
      {
        id,
        agent,
        role: "Registered locally — mock only",
        principal: previewPrincipal,
        grants: GRANT_OPTIONS.map((g) => g.id).filter((g) => grants.has(g)),
      },
    ]);
    setOpen(false);
    resetDialog();
  };

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) resetDialog();
        }}
      >
        <DialogContent className="max-w-lg bg-[var(--bg-primary)] border-[var(--border-color)]">
          <DialogHeader>
            <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">
              Register principal
            </DialogTitle>
            <DialogDescription className="text-xs text-[var(--text-secondary)]">
              This is who the agent is. Vertex accepts the SPIFFE id. There is no API key on this tab.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-1">
            <div className="space-y-1.5">
              <Label className="text-xs text-[var(--text-secondary)]">Agent name</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Policy"
                className="h-8 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-xs text-[var(--text-secondary)]">IAM grants</Label>
              <div className="rounded-lg border border-[var(--border-color)] divide-y divide-[var(--border-color)]">
                {GRANT_OPTIONS.map((opt) => (
                  <label
                    key={opt.id}
                    className="flex items-start gap-2.5 px-3 py-2 text-xs cursor-pointer hover:bg-[var(--bg-tertiary)]"
                  >
                    <Checkbox
                      checked={grants.has(opt.id)}
                      onCheckedChange={(v) => {
                        setGrants((prev) => {
                          const next = new Set(prev);
                          if (v === true) next.add(opt.id);
                          else next.delete(opt.id);
                          return next;
                        });
                      }}
                      className="mt-0.5 border-[var(--border-color)] data-[state=checked]:bg-primary data-[state=checked]:border-primary"
                    />
                    <span>
                      <span className="font-mono text-[var(--text-primary)]">{opt.label}</span>
                      <span className="block text-[10px] text-[var(--text-secondary)] mt-0.5">{opt.hint}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-[var(--text-secondary)]">Principal preview</Label>
              <p className="font-mono text-[10px] leading-relaxed text-[var(--text-secondary)] bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-md px-2.5 py-2 break-all">
                {previewPrincipal}
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setOpen(false)}
              className="text-xs border-[var(--border-color)] text-[var(--text-primary)]"
            >
              Cancel
            </Button>
            <Button
              onClick={register}
              disabled={!name.trim() || grants.size === 0}
              className="text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
            >
              Register
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="h-full overflow-y-auto bg-[var(--bg-primary)] min-w-0">
        <div className="p-6 space-y-6">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">Agent Identity</h2>
              <p className="text-xs text-[var(--text-secondary)] mt-1 leading-relaxed">
                Who the agent is. A SPIFFE principal. You grant that principal{" "}
                <span className="font-mono">aiplatform.user</span>. Vertex accepts the agent itself.
              </p>
            </div>
            <Button
              size="sm"
              onClick={() => setOpen(true)}
              className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
            >
              <Plus className="h-3 w-3 mr-1" />
              Register principal
            </Button>
          </div>

          <div className="bg-primary/10 border border-primary/20 rounded-lg p-4">
            <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
              <span className="font-medium text-primary">No API key on this tab.</span> The badge is the
              principal. The model never receives a credential. Mock layout — nothing is written to IAM yet.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)] p-3">
              <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
                Project
              </p>
              <p className="mt-1 font-mono text-[12px] text-[var(--text-primary)]">patch-505223</p>
            </div>
            <div className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)] p-3">
              <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-secondary)]">
                Runtime
              </p>
              <p className="mt-1 text-[12px] text-[var(--text-primary)]">Gemini 3.5 Flash · global</p>
            </div>
          </div>

          <div className="rounded-lg border border-[var(--border-color)] overflow-hidden">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-[var(--border-color)] bg-[var(--bg-secondary)]">
                  <th className="py-1.5 px-3 text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                    Agent
                  </th>
                  <th className="py-1.5 px-3 text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                    Principal
                  </th>
                  <th className="py-1.5 px-3 text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                    Grants
                  </th>
                  <th className="py-1.5 px-3 text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider w-20">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.id}
                    className="border-b border-[var(--border-color)] last:border-b-0 hover:bg-[var(--bg-tertiary)] text-xs"
                  >
                    <td className="py-2.5 px-3 align-top">
                      <div className="flex items-start gap-2">
                        <Fingerprint className="h-3.5 w-3.5 mt-0.5 shrink-0 text-[var(--text-secondary)]" />
                        <div>
                          <p className="font-medium text-[var(--text-primary)]">{row.agent}</p>
                          <p className="text-[10px] text-[var(--text-secondary)] mt-0.5">{row.role}</p>
                        </div>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 align-top">
                      <p
                        className="font-mono text-[10px] text-[var(--text-secondary)] truncate max-w-[16rem]"
                        title={row.principal}
                      >
                        {shortPrincipal(row.principal)}
                      </p>
                    </td>
                    <td className="py-2.5 px-3 align-top">
                      <div className="flex flex-wrap gap-1">
                        {row.grants.map((g) => (
                          <Badge
                            key={g}
                            variant="outline"
                            className="text-[9px] font-mono font-normal text-[var(--text-secondary)]"
                          >
                            {g}
                          </Badge>
                        ))}
                      </div>
                    </td>
                    <td className="py-2.5 px-3 align-top whitespace-nowrap">
                      <span className="inline-flex items-center gap-1 text-[10px] text-[#10b981]">
                        <Shield className="h-3 w-3" />
                        Attested
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className={cn("text-[10px] text-[var(--text-secondary)] leading-relaxed")}>
            Denied by default: merge, admin, secret rotation, and any raw token. Extra grants are explicit IAM
            bindings on the principal, not prompt instructions.
          </p>
        </div>
      </div>
    </>
  );
}
