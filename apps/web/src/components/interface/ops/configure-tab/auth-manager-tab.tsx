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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus, Vault } from "lucide-react";

type ProviderKind = "api_key" | "oauth2" | "oauth3";

type ProviderRow = {
  id: string;
  name: string;
  kind: ProviderKind;
  usedBy: string;
  principal: string;
};

const KIND_LABEL: Record<ProviderKind, string> = {
  api_key: "API key",
  oauth2: "2-legged OAuth",
  oauth3: "3-legged OAuth",
};

const INITIAL: ProviderRow[] = [
  {
    id: "gemini-api",
    name: "gemini-api",
    kind: "api_key",
    usedBy: "Egaki live verification",
    principal: "verification",
  },
  {
    id: "github-app",
    name: "github-app",
    kind: "oauth2",
    usedBy: "PR publisher (not an agent)",
    principal: "github-tools",
  },
];

export function AuthManagerTab() {
  const [rows, setRows] = useState(INITIAL);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<ProviderKind>("api_key");
  const [usedBy, setUsedBy] = useState("");

  const resetDialog = () => {
    setName("");
    setKind("api_key");
    setUsedBy("");
  };

  const register = () => {
    const n = name.trim();
    if (!n) return;
    setRows((prev) => [
      ...prev,
      {
        id: `${n}-${prev.length + 1}`,
        name: n,
        kind,
        usedBy: usedBy.trim() || "Named tool call",
        principal: "patch",
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
              Register vault provider
            </DialogTitle>
            <DialogDescription className="text-xs text-[var(--text-secondary)]">
              The agent still authenticates with its SPIFFE id. The manager attaches the credential on the
              outbound call. The model never sees the value.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-1">
            <div className="space-y-1.5">
              <Label className="text-xs text-[var(--text-secondary)]">Provider name</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. gemini-api"
                className="h-8 text-xs font-mono bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-[var(--text-secondary)]">Kind</Label>
              <Select value={kind} onValueChange={(v) => setKind(v as ProviderKind)}>
                <SelectTrigger className="h-8 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
                  <SelectItem value="api_key" className="text-xs">
                    API key
                  </SelectItem>
                  <SelectItem value="oauth2" className="text-xs">
                    2-legged OAuth
                  </SelectItem>
                  <SelectItem value="oauth3" className="text-xs">
                    3-legged OAuth
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-[var(--text-secondary)]">Used by</Label>
              <Input
                value={usedBy}
                onChange={(e) => setUsedBy(e.target.value)}
                placeholder="e.g. Egaki live verification"
                className="h-8 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]"
              />
            </div>
            <div className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)] px-3 py-2.5">
              <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
                No value field. The payload is created in the vault later. This dialog only registers the
                provider name the agent is allowed to request.
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
              disabled={!name.trim()}
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
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">Auth manager</h2>
              <p className="text-xs text-[var(--text-secondary)] mt-1 leading-relaxed">
                A vault the agent is allowed to use. The same SPIFFE id opens it. A stored key or OAuth
                token is attached on the tool call — never placed in the prompt.
              </p>
            </div>
            <Button
              size="sm"
              onClick={() => setOpen(true)}
              className="h-8 text-xs bg-primary hover:bg-primary/90 text-primary-foreground"
            >
              <Plus className="h-3 w-3 mr-1" />
              Register provider
            </Button>
          </div>

          <div className="bg-primary/10 border border-primary/20 rounded-lg p-4">
            <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
              <span className="font-medium text-primary">Names only in this list.</span> Agents request{" "}
              <span className="font-mono">gemini-api</span>. The vault injects the header. Mock layout —
              nothing is written to auth manager yet.
            </p>
          </div>

          <div className="rounded-lg border border-[var(--border-color)] overflow-hidden">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-[var(--border-color)] bg-[var(--bg-secondary)]">
                  <th className="py-1.5 px-3 text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                    Provider
                  </th>
                  <th className="py-1.5 px-3 text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                    Kind
                  </th>
                  <th className="py-1.5 px-3 text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                    Used by
                  </th>
                  <th className="py-1.5 px-3 text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                    Secret
                  </th>
                  <th className="py-1.5 px-3 text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider w-16">
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
                    <td className="py-2.5 px-3 align-middle">
                      <div className="flex items-center gap-2">
                        <Vault className="h-3.5 w-3.5 shrink-0 text-[var(--text-secondary)]" />
                        <span className="font-mono text-[11px] text-[var(--text-primary)]">{row.name}</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 align-middle">
                      <Badge
                        variant="outline"
                        className="text-[9px] font-normal text-[var(--text-secondary)]"
                      >
                        {KIND_LABEL[row.kind]}
                      </Badge>
                    </td>
                    <td className="py-2.5 px-3 align-middle text-[var(--text-secondary)]">
                      {row.usedBy}
                    </td>
                    <td className="py-2.5 px-3 align-middle">
                      <span className="text-[10px] text-[var(--text-secondary)]">Never exposed</span>
                    </td>
                    <td className="py-2.5 px-3 align-middle whitespace-nowrap">
                      <span className="inline-flex items-center gap-1 text-[10px] text-[#10b981]">
                        <span className="h-1.5 w-1.5 rounded-full bg-[#10b981] inline-block" />
                        Active
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
            Identity is the badge. Auth manager is the drawer that badge can open. Connection and Secrets
            stay as they are until this vault replaces raw key paste.
          </p>
        </div>
      </div>
    </>
  );
}
