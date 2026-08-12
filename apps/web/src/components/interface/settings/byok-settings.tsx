"use client";

import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import {
  AlertCircle,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  MoreHorizontal,
  Pencil,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Display names = API vendor (matches how users get keys). Backend still uses openai | anthropic | google. */
const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  google: "Google",
};

type SavedKeyEntry = {
  id: string;
  provider: string;
  providerLabel: string;
  alias: string;
  maskedKey: string;
  savedAtLabel: string;
};

type ApiKeyResponse = {
  id: string;
  team_id: string;
  provider: string;
  alias: string;
  masked_key: string;
  created_by: string;
  created_at: string | null;
  updated_at: string | null;
};

function toEntry(k: ApiKeyResponse): SavedKeyEntry {
  return {
    id: k.id,
    provider: k.provider,
    providerLabel: PROVIDER_LABELS[k.provider] ?? k.provider,
    alias: k.alias,
    maskedKey: k.masked_key,
    savedAtLabel: k.created_at
      ? new Date(k.created_at).toLocaleString(undefined, {
          month: "short",
          day: "numeric",
          year: "numeric",
          hour: "numeric",
          minute: "2-digit",
        })
      : "",
  };
}

function validateApiKey(provider: string, key: string): string | null {
  const t = key.trim();
  if (!t) return "Enter an API key.";

  switch (provider) {
    case "openai":
      if (!t.startsWith("sk-") || t.length < 20)
        return "OpenAI keys usually start with sk- and are at least 20 characters.";
      break;
    case "anthropic":
      if (!t.startsWith("sk-ant-") || t.length < 20)
        return "Anthropic keys usually start with sk-ant-.";
      break;
    case "google":
      if (!t.startsWith("AIza") || t.length < 30)
        return "Google AI Studio keys (for Gemini) often start with AIza and are longer than 30 characters.";
      break;
    default:
      if (t.length < 8) return "That key looks too short.";
  }
  return null;
}

const fieldInputClass =
  "h-9 text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] focus-visible:border-primary focus-visible:ring-1 focus-visible:ring-primary/25";

const selectTriggerClass = cn(
  "h-9 w-full text-sm shadow-sm transition-colors",
  "bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]",
  "hover:bg-[var(--bg-tertiary)]",
  "[&>span]:text-[var(--text-primary)] data-[placeholder]:text-[var(--text-secondary)]",
  "[&_svg]:text-[var(--text-secondary)] [&_svg]:opacity-80",
  "focus:ring-1 focus:ring-primary/25 focus:border-primary"
);

const selectContentClass = cn(
  "z-[200] overflow-hidden rounded-md border shadow-lg",
  "border-[var(--border-color)] bg-[var(--bg-primary)] text-[var(--text-primary)]"
);

const selectItemClass = cn(
  "cursor-pointer rounded-sm py-2 pl-2 pr-8 text-sm outline-none",
  "text-[var(--text-primary)]",
  "hover:bg-[var(--bg-tertiary)] focus:bg-[var(--bg-tertiary)]",
  "data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
);

export function ByokSettings() {
  const [orgId, setOrgId] = useState<string | null>(null);
  const [provider, setProvider] = useState("openai");
  const [apiKey, setApiKey] = useState("");
  const [keyAlias, setKeyAlias] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [keyError, setKeyError] = useState<string | null>(null);
  const [savedHint, setSavedHint] = useState<string | null>(null);
  const [savedKeys, setSavedKeys] = useState<SavedKeyEntry[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<SavedKeyEntry | null>(null);
  const [renameTarget, setRenameTarget] = useState<SavedKeyEntry | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchOrg = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/organizations/current`, {
        credentials: "include",
      });
      if (!res.ok) {
        setOrgId(null);
        setSavedKeys([]);
        setLoading(false);
        return;
      }
      const data = await res.json();
      setOrgId(data.id);
    } catch {
      setOrgId(null);
      setSavedKeys([]);
      setLoading(false);
    }
  }, []);

  const fetchKeys = useCallback(async (oid: string) => {
    try {
      const res = await fetch(`${API_URL}/api/organizations/${oid}/byok`, {
        credentials: "include",
      });
      if (!res.ok) return;
      const data = await res.json();
      setSavedKeys((data.keys as ApiKeyResponse[]).map(toEntry));
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOrg();
  }, [fetchOrg]);

  useEffect(() => {
    if (orgId) fetchKeys(orgId);
  }, [orgId, fetchKeys]);

  const handleSaveKey = async () => {
    const err = validateApiKey(provider, apiKey);
    setKeyError(err);
    if (err) {
      setSavedHint(null);
      return;
    }
    if (!orgId) {
      setKeyError("Organization not loaded. Please refresh.");
      return;
    }

    setSaving(true);
    setSavedHint(null);
    try {
      const res = await fetch(`${API_URL}/api/organizations/${orgId}/byok`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          provider,
          api_key: apiKey,
          alias: keyAlias.trim() || PROVIDER_LABELS[provider] || provider,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setKeyError(body.detail || `Save failed (${res.status})`);
        return;
      }

      const saved: ApiKeyResponse = await res.json();
      setSavedKeys((prev) => {
        const filtered = prev.filter((k) => k.provider !== saved.provider);
        return [toEntry(saved), ...filtered];
      });
      setApiKey("");
      setKeyAlias("");
      setShowApiKey(false);
      setSavedHint("Key saved. It will be used for model requests on your next run.");
    } catch (e) {
      setKeyError(`Network error: ${e}`);
    } finally {
      setSaving(false);
    }
  };

  const handleRenameSave = async () => {
    if (!renameTarget || !orgId || !renameDraft.trim()) return;
    setRenaming(true);
    try {
      const res = await fetch(
        `${API_URL}/api/organizations/${orgId}/byok/${renameTarget.id}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ alias: renameDraft.trim() }),
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        console.error(body.detail || res.statusText);
        return;
      }
      const updated: ApiKeyResponse = await res.json();
      setSavedKeys((prev) =>
        prev.map((k) => (k.id === updated.id ? toEntry(updated) : k))
      );
      setRenameTarget(null);
      setRenameDraft("");
    } finally {
      setRenaming(false);
    }
  };

  const handleDeleteKey = async () => {
    if (!deleteTarget || !orgId) return;
    setDeleting(true);
    try {
      const res = await fetch(
        `${API_URL}/api/organizations/${orgId}/byok/${deleteTarget.id}`,
        { method: "DELETE", credentials: "include" }
      );
      if (res.ok) {
        setSavedKeys((prev) => prev.filter((k) => k.id !== deleteTarget.id));
      }
    } catch {
      /* ignore */
    } finally {
      setDeleting(false);
      setDeleteTarget(null);
    }
  };

  return (
    <div className="max-w-xl mx-auto px-6 py-8 space-y-8">
      <div>
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-1">
          Bring your own API key
        </h2>
        <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
          Add your cloud provider API key so JetRun can run models on your behalf. Traffic uses the model
          gateway your organization runs, so billing and credentials stay under your control.
        </p>
      </div>

      <div className="bg-primary/10 border border-primary/20 rounded-lg p-4">
        <div className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
          <span className="font-medium text-primary">Your keys stay protected:</span> Encrypted at rest and
          used only with your gateway. JetRun does not call provider APIs directly.
        </div>
      </div>

      <div className="space-y-5">
        <div className="grid gap-2">
          <Label className="text-xs text-[var(--text-secondary)]">Provider</Label>
          <Select
            value={provider}
            onValueChange={(v) => {
              setProvider(v);
              setKeyError(null);
            }}
          >
            <SelectTrigger className={selectTriggerClass}>
              <SelectValue placeholder="Select provider" />
            </SelectTrigger>
            <SelectContent className={selectContentClass}>
              <SelectItem className={selectItemClass} value="openai">OpenAI</SelectItem>
              <SelectItem className={selectItemClass} value="anthropic">Anthropic</SelectItem>
              <SelectItem className={selectItemClass} value="google">Google</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-[10px] text-[var(--text-secondary)]">
            Pick the vendor that issued the key (e.g. Gemini models use Google AI Studio keys).
          </p>
        </div>

        <div className="grid gap-2">
          <Label className="text-xs text-[var(--text-secondary)]">API key</Label>
          <div className="relative">
            <Input
              type={showApiKey ? "text" : "password"}
              autoComplete="off"
              placeholder={provider === "google" ? "AIza…" : "sk-…"}
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value);
                if (keyError) setKeyError(null);
                setSavedHint(null);
              }}
              className={cn(fieldInputClass, "pr-10")}
            />
            <button
              type="button"
              onClick={() => setShowApiKey((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              aria-label={showApiKey ? "Hide API key" : "Show API key"}
            >
              {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          {keyError ? (
            <div className="flex items-center gap-2">
              <AlertCircle className="h-3.5 w-3.5 text-red-400 flex-shrink-0" />
              <p className="text-[10px] text-red-400">{keyError}</p>
            </div>
          ) : (
            <p className="text-[10px] text-[var(--text-secondary)]">
              Never shown in chat. Keys are encrypted at rest and used only with your model gateway.
            </p>
          )}
        </div>

        <div className="grid gap-2">
          <Label className="text-xs text-[var(--text-secondary)]">Key alias (optional)</Label>
          <Input
            placeholder="e.g. team-prod-openai"
            value={keyAlias}
            onChange={(e) => setKeyAlias(e.target.value)}
            className={fieldInputClass}
          />
          <p className="text-[10px] text-[var(--text-secondary)]">
            Optional label for your gateway and for finding this key in JetRun later.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-3 pt-2">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <Button
            type="button"
            className="bg-primary hover:bg-primary-hover text-primary-foreground h-9 text-xs w-fit"
            onClick={handleSaveKey}
            disabled={saving || !orgId}
          >
            {saving ? (
              <>
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                Saving…
              </>
            ) : (
              "Save key"
            )}
          </Button>
          {savedHint ? (
            <p className="text-[11px] text-[var(--text-secondary)]">{savedHint}</p>
          ) : null}
        </div>

        <div className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-primary)] overflow-hidden">
          <div className="px-3 py-2 border-b border-[var(--border-color)] bg-[var(--bg-secondary)]/50">
            <p className="text-[11px] font-medium text-[var(--text-primary)]">Saved keys</p>
          </div>
          {loading ? (
            <div className="px-3 py-6 flex items-center justify-center">
              <Loader2 className="h-4 w-4 animate-spin text-[var(--text-secondary)]" />
            </div>
          ) : !orgId ? (
            <div className="px-3 py-8 flex flex-col items-center gap-2 text-center">
              <div className="rounded-full bg-[var(--bg-tertiary)] p-2.5 text-[var(--text-secondary)]">
                <KeyRound className="h-4 w-4" aria-hidden />
              </div>
              <p className="text-[11px] font-medium text-[var(--text-primary)]">Sign in to manage keys</p>
              <p className="text-[10px] text-[var(--text-secondary)] max-w-[16rem] leading-relaxed">
                Saved keys are tied to your organization. Sign in to add, rename, or remove API keys.
              </p>
            </div>
          ) : savedKeys.length === 0 ? (
            <div className="px-3 py-8 flex flex-col items-center gap-2 text-center">
              <div className="rounded-full bg-[var(--bg-tertiary)] p-2.5 text-[var(--text-secondary)]">
                <KeyRound className="h-4 w-4" aria-hidden />
              </div>
              <p className="text-[11px] font-medium text-[var(--text-primary)]">No saved keys yet</p>
              <p className="text-[10px] text-[var(--text-secondary)] max-w-[16rem] leading-relaxed">
                Add a provider key above and click Save key. It will appear here with a masked preview.
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-[var(--border-color)]">
              {savedKeys.map((row) => (
                <li key={row.id} className="px-3 py-2.5 flex items-start gap-2 sm:items-center">
                  <div className="min-w-0 flex-1">
                    <p className="text-[11px] font-medium text-[var(--text-primary)] truncate">{row.alias}</p>
                    <p className="text-[10px] text-[var(--text-secondary)]">
                      {row.providerLabel}
                      <span className="text-[var(--border-color)] mx-1.5">·</span>
                      <span className="font-mono">{row.maskedKey}</span>
                    </p>
                    <p className="text-[10px] text-[var(--text-secondary)] sm:hidden mt-0.5">
                      {row.savedAtLabel}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <p className="text-[10px] text-[var(--text-secondary)] text-right hidden sm:block max-w-[7rem] truncate">
                      {row.savedAtLabel}
                    </p>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button
                          type="button"
                          className="h-7 w-7 flex items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] transition-colors"
                          aria-label="Key actions"
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent
                        align="end"
                        className="w-48 bg-[var(--bg-primary)] border-[var(--border-color)]"
                      >
                        <DropdownMenuItem
                          className="flex items-center gap-2 p-2 cursor-pointer hover:bg-[var(--bg-tertiary)] focus:bg-[var(--bg-tertiary)]"
                          onClick={() => {
                            setRenameTarget(row);
                            setRenameDraft(row.alias);
                          }}
                        >
                          <Pencil className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
                          <span className="text-xs text-[var(--text-primary)]">Rename key</span>
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="flex items-center gap-2 p-2 cursor-pointer hover:bg-red-500/10 focus:bg-red-500/10"
                          onClick={() => setDeleteTarget(row)}
                        >
                          <Trash2 className="h-3.5 w-3.5 text-red-500" />
                          <span className="text-xs text-red-500">Delete key</span>
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <Dialog
        open={renameTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setRenameTarget(null);
            setRenameDraft("");
          }
        }}
      >
        <DialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)] sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">Rename key</DialogTitle>
          </DialogHeader>
          <div className="grid gap-2 py-2">
            <Label className="text-xs text-[var(--text-secondary)]">Display name</Label>
            <Input
              value={renameDraft}
              onChange={(e) => setRenameDraft(e.target.value)}
              className={fieldInputClass}
              placeholder="Key label"
            />
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              type="button"
              variant="outline"
              className="text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
              onClick={() => {
                setRenameTarget(null);
                setRenameDraft("");
              }}
            >
              Cancel
            </Button>
            <Button
              type="button"
              className="bg-primary hover:bg-primary-hover text-primary-foreground text-xs"
              disabled={!renameDraft.trim() || renaming}
              onClick={handleRenameSave}
            >
              {renaming ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <AlertDialogContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-base text-[var(--text-primary)]">
              {deleteTarget ? `Delete "${deleteTarget.alias}"?` : ""}
            </AlertDialogTitle>
            <AlertDialogDescription className="text-sm text-[var(--text-secondary)] leading-relaxed">
              This removes the key from your organization. Runs will fall back to the platform key.
              You can add a new key later.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-500 hover:bg-red-600 text-white focus:ring-red-500 sm:mt-0"
              disabled={deleting}
              onClick={handleDeleteKey}
            >
              {deleting ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
