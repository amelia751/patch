"use client";

import React, { useState, useCallback, useContext, createContext, useEffect } from "react";
import { cn } from "@/lib/utils";
import { useTheme } from "@/lib/theme-context";
import { useAuth } from "@/lib/auth-context";

// =============================================================================
// Project Context - Shared state for project management
// =============================================================================
interface ProjectContextType {
  projects: Project[];
  currentProject: Project | null;
  isLoading: boolean;
  refreshProjects: () => Promise<void>;
  setCurrentProject: (project: Project | null) => void;
}

const ProjectContext = createContext<ProjectContextType | null>(null);

export function useProjects() {
  const context = useContext(ProjectContext);
  if (!context) {
    // Return mock context when not wrapped in provider
    return {
      projects: [],
      currentProject: null,
      isLoading: false,
      refreshProjects: async () => {},
      setCurrentProject: () => {},
    };
  }
  return context;
}
import mockInfo from "../shared/mock-aws/mock-info.json";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Cloud,
  Plus,
  ChevronDown,
  ChevronRight,
  Settings,
  ArrowRight,
  FolderOpen,
  Github,
  Globe,
  Star,
  Lock,
  Copy,
  Trash2,
  Check,
  ExternalLink,
  GitBranch,
  BellRing,
  KeyRound,
  AlertTriangle,
  Sparkles,
  PackagePlus,
  Layers,
  Loader2,
  MonitorCloud,
} from "lucide-react";
import { Spinner } from "@/components/ui/spinner";

// Import mock data
const mockProjects = mockInfo.mockProjects;
const mockGitHubRepos = mockInfo.mockGitHubRepos;

// ============================================================================
// Project Settings Dialog
// ============================================================================
export function ProjectSettingsDialog({
  open,
  onOpenChange,
  project,
  onProjectDeleted,
  onProjectUpdated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project: { id: string; name: string; status: string };
  onProjectDeleted?: () => void;
  onProjectUpdated?: (project: { id: string; name: string; status: string }) => void;
}) {
  const { isAuthenticated } = useAuth();
  const [activeTab, setActiveTab] = useState("general");
  const [projectName, setProjectName] = useState(project.name);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setProjectName(project.name);
      setSaveError(null);
      setActiveTab((t) => (t === "environment" ? "general" : t));
    }
  }, [open, project.id, project.name]);

  const tabs = [
    { id: "general", label: "General", icon: Settings },
    // { id: "integrations", label: "Integrations", icon: GitBranch },
    { id: "danger", label: "Danger Zone", icon: Trash2 },
  ];

  const deleteConfirmMatches =
    deleteConfirmText.trim() === project.name.trim();

  const handleDeleteProject = async () => {
    if (!isAuthenticated) return;
    if (!project?.id) {
      setDeleteError("Project ID is missing. Refresh the page and try again.");
      return;
    }
    if (!deleteConfirmMatches) return;

    setIsDeleting(true);
    setDeleteError(null);
    
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const response = await fetch(`${API_URL}/api/projects/${project.id}`, {
        method: "DELETE",
        credentials: "include",
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Failed to delete project");
      }

      // Close dialogs and refresh project list
      setShowDeleteConfirm(false);
      onOpenChange(false);
      if (onProjectDeleted) {
        onProjectDeleted();
      }
    } catch (err: any) {
      console.error("Error deleting project:", err);
      setDeleteError(err.message || "Failed to delete project");
    } finally {
      setIsDeleting(false);
    }
  };

  const handleSaveGeneral = async () => {
    if (!isAuthenticated) return;
    if (!project?.id) {
      setSaveError("Project ID is missing. Refresh the page and try again.");
      return;
    }
    const trimmed = projectName.trim();
    if (!trimmed) {
      setSaveError("Project name cannot be empty.");
      return;
    }
    if (trimmed === project.name) {
      setSaveError(null);
      return;
    }

    setIsSaving(true);
    setSaveError(null);
    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    try {
      const response = await fetch(`${API_URL}/api/projects/${project.id}`, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: trimmed }),
      });
      if (!response.ok) {
        let message = "Failed to update project";
        try {
          const err = await response.json();
          message = err.detail || message;
        } catch {
          // ignore
        }
        throw new Error(message);
      }
      const data = await response.json();
      onProjectUpdated?.({ id: data.id, name: data.name, status: data.status });
    } catch (err: any) {
      console.error("Error saving project name:", err);
      setSaveError(err.message || "Failed to update project name");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl bg-[var(--bg-primary)] border-[var(--border-color)] p-0">
        <div className="flex h-[500px] pt-3">
          {/* Sidebar */}
          <div className="w-48 border-r border-[var(--border-color)] p-4 bg-[var(--bg-secondary)]/30">
            <DialogHeader className="mb-4">
              <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">Project Settings</DialogTitle>
              <DialogDescription className="text-[10px] text-[var(--text-secondary)]">{project.name}</DialogDescription>
            </DialogHeader>
            <nav className="space-y-1">
              {tabs.map((tab) => (
          <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    "w-full flex items-center gap-2.5 px-3 py-2 text-xs rounded-lg transition-all duration-200",
                    activeTab === tab.id
                      ? tab.id === "danger" ? "bg-red-500 text-white shadow-sm" : "bg-primary text-primary-foreground shadow-sm"
                      : tab.id === "danger"
                        ? "text-red-500 hover:bg-red-500/10"
                        : "text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
                  )}
                >
                  <tab.icon className="h-3.5 w-3.5" />
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>

          {/* Content */}
          <div className="flex-1 p-6 overflow-y-auto">
            {activeTab === "general" && (
              <div className="space-y-6">
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">General Settings</h3>
                <div className="grid gap-4">
                  <div className="grid gap-2">
                    <Label className="text-xs text-[var(--text-secondary)]">Project Name</Label>
                    <Input
                      value={projectName}
                      onChange={(e) => {
                        setProjectName(e.target.value);
                        if (saveError) setSaveError(null);
                      }}
                      disabled={!isAuthenticated}
                      className="h-9 text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] focus:border-primary focus:ring-primary/20"
                    />
                  </div>
                  {/* <div className="grid gap-2">
                    <Label className="text-xs text-[var(--text-secondary)]">Description</Label>
                    <Textarea placeholder="Add a description..." className="text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] resize-none focus:border-primary focus:ring-primary/20" rows={3} />
                  </div> */}
                  <div className="grid gap-2">
                    <Label className="text-xs text-[var(--text-secondary)]">Project ID</Label>
        <div className="flex items-center gap-2">
                      <Input defaultValue={project.id} readOnly className="h-9 text-sm bg-[var(--bg-tertiary)] border-[var(--border-color)] text-[var(--text-secondary)] font-mono" />
                      <Button variant="outline" size="sm" className="h-9 px-3 border-[var(--border-color)] hover:bg-[var(--bg-tertiary)]">
                        <Copy className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
                      </Button>
                    </div>
                  </div>
                </div>
                {saveError && (
                  <p className="text-[10px] text-red-500">{saveError}</p>
                )}
                <div className="flex items-center justify-end gap-2 pt-4 border-t border-[var(--border-color)]">
                  <Button
                    size="sm"
                    onClick={handleSaveGeneral}
                    disabled={!isAuthenticated || isSaving || projectName.trim() === project.name}
                    className="bg-primary hover:bg-primary-hover text-primary-foreground text-xs shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isSaving ? (
                      <>
                        <Spinner className="h-3 w-3 mr-1.5" />
                        Saving...
                      </>
                    ) : (
                      "Save Changes"
                    )}
                  </Button>
                </div>
              </div>
            )}

            {/* {activeTab === "integrations" && (
              <div className="space-y-6">
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">Integrations</h3>
                <div className="space-y-3">
                  <div className="flex items-center justify-between p-4 rounded-xl border border-[var(--border-color)] bg-[var(--bg-secondary)]/30">
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 rounded-lg bg-[var(--bg-tertiary)] flex items-center justify-center">
                        <Github className="h-5 w-5 text-[var(--text-primary)]" />
                      </div>
                      <div>
                        <p className="text-xs font-medium text-[var(--text-primary)]">GitHub</p>
                        <p className="text-[10px] text-[var(--text-secondary)]">Connected to {mockInfo.githubIntegration.connectedTo}</p>
                      </div>
                    </div>
                    <span className="text-[10px] px-2.5 py-1 rounded-full bg-[#10b981]/10 text-[#10b981] font-medium">Connected</span>
                  </div>
                  <div className="flex items-center justify-between p-4 rounded-xl border border-dashed border-[var(--border-color)] bg-[var(--bg-secondary)]/20">
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 rounded-lg bg-[var(--bg-tertiary)] flex items-center justify-center">
                        <Cloud className="h-5 w-5 text-[var(--text-secondary)]" />
                      </div>
                      <div>
                        <p className="text-xs font-medium text-[var(--text-primary)]">AWS</p>
                        <p className="text-[10px] text-[var(--text-secondary)]">Deploy to AWS infrastructure</p>
                      </div>
                    </div>
                    <Button size="sm" variant="outline" className="text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]">Connect</Button>
                  </div>
                </div>
              </div>
            )} */}

            {activeTab === "danger" && (
              <div className="space-y-6">
                <h3 className="text-sm font-semibold text-red-500">Danger Zone</h3>
                <div className="p-5 rounded-xl border-2 border-red-500/20">
                  <h4 className="text-xs font-semibold text-[var(--text-primary)] mb-2">Remove project</h4>
                  <p className="text-[11px] text-[var(--text-secondary)] mb-4 leading-relaxed">
                    All conversation threads and other project data we store are permanently deleted. Linked GitHub
                    repositories are only disconnected—we do not delete or change your repositories on GitHub.
                  </p>
                  {!showDeleteConfirm ? (
                    <Button 
                      size="sm" 
                      variant="destructive" 
                      className="text-xs bg-red-500 hover:bg-red-600 text-white"
                      onClick={() => setShowDeleteConfirm(true)}
                      disabled={!isAuthenticated}
                    >
                      Remove project
                    </Button>
                  ) : (
                    <div className="space-y-3 pt-2 border-t border-red-500/20">
                      <p className="text-[10px] text-[var(--text-secondary)]">
                        Type{" "}
                        <strong className="text-red-500">{project.name}</strong>
                        {" "}
                        to confirm (exact match, surrounding spaces ignored):
                      </p>
                      <Input
                        value={deleteConfirmText}
                        onChange={(e) => setDeleteConfirmText(e.target.value)}
                        placeholder="Type project name to confirm"
                        className="h-9 text-sm bg-[var(--bg-secondary)] border-red-500/30 text-[var(--text-primary)] focus:border-red-500 focus:ring-red-500/20"
                      />
                      {deleteError && (
                        <p className="text-[10px] text-red-500">{deleteError}</p>
                      )}
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                          onClick={() => {
                            setShowDeleteConfirm(false);
                            setDeleteConfirmText("");
                            setDeleteError(null);
                          }}
                        >
                          Cancel
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          className="text-xs bg-red-500 hover:bg-red-600 text-white"
                          onClick={handleDeleteProject}
                          disabled={!deleteConfirmMatches || isDeleting}
                        >
                          {isDeleting ? (
                            <>
                              <Spinner className="h-3 w-3 mr-1.5" />
                              <span className="shimmer-text">Deleting</span>
                            </>
                          ) : (
                            "Remove project"
                          )}
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================================
// New Project Dialog
// ============================================================================
export function NewProjectDialog({
  open,
  onOpenChange,
  onProjectCreated,
  onGoToProject,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onProjectCreated?: () => void;
  onGoToProject?: (project: { id: string; name: string; status: string }) => void;
}) {
  const { isAuthenticated, user } = useAuth();
  const [backendRepoName, setBackendRepoName] = useState("");
  const [repoVisibility, setRepoVisibility] = useState<"public" | "private">("private");
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showLinkDialog, setShowLinkDialog] = useState(false);
  const isGitHubLinked = user?.github_app_installed ?? false;

  useEffect(() => {
    if (open) {
      if (!isGitHubLinked) {
        setShowLinkDialog(true);
        onOpenChange(false);
        return;
      }
      setError(null);
      if (!backendRepoName) {
        setBackendRepoName("");
      }
    }
  }, [open, isGitHubLinked, onOpenChange, backendRepoName]);

  const handleCreateProject = async () => {
    if (!isAuthenticated) {
      setError("Sign in to create a backend project.");
      return;
    }

    if (!backendRepoName.trim()) {
      setError("Repository name is required.");
      return;
    }

    setIsCreating(true);
    setError(null);

    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const response = await fetch(`${API_URL}/api/projects/`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: backendRepoName.trim(),
          repo_name: backendRepoName.trim(),
          repo_visibility: repoVisibility,
        }),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Failed to create project");
      }

      const project = await response.json();
      onOpenChange(false);
      if (onProjectCreated) {
        onProjectCreated();
      }
      if (onGoToProject) {
        onGoToProject({ id: project.id, name: project.name, status: project.status || "draft" });
      }
    } catch (err: any) {
      console.error("Error creating project:", err);
      setError(err.message || "Failed to create project");
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-md bg-[var(--bg-primary)] border-[var(--border-color)]">
          <DialogHeader>
            <div className="flex items-center gap-3 mb-2">
              <div className="h-10 w-10 rounded-xl bg-primary/10 border border-primary/30 flex items-center justify-center">
                <Layers className="h-5 w-5 text-primary" />
              </div>
              <div>
                <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">Set Up Backend Repository</DialogTitle>
                <DialogDescription className="text-xs text-[var(--text-secondary)]">
                  Create a new repository for your backend code
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            {error && (
              <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
              </div>
            )}

            {/* Backend Repository Name */}
            <div className="grid gap-2">
              <Label className="text-xs text-[var(--text-secondary)]">Backend Repository Name</Label>
              <Input
                value={backendRepoName}
                onChange={(e) => {
                  setBackendRepoName(e.target.value);
                }}
                placeholder="backend-repository"
                disabled={isCreating}
                className="h-10 text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] focus:border-primary focus:ring-primary/20 disabled:opacity-50"
              />
            </div>

            {/* Visibility */}
            <div className="grid gap-2">
              <Label className="text-xs text-[var(--text-secondary)]">Visibility</Label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => setRepoVisibility("public")}
                  disabled={isCreating}
                  className={cn(
                    "p-3 rounded-lg border-2 transition-all duration-200 text-left disabled:opacity-50",
                    repoVisibility === "public"
                      ? "border-primary bg-primary/5"
                      : "border-[var(--border-color)] hover:border-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]/50"
                  )}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Globe className={cn(
                      "h-3.5 w-3.5",
                      repoVisibility === "public" ? "text-primary" : "text-[var(--text-secondary)]"
                    )} />
                    <p className="text-xs font-medium text-[var(--text-primary)]">Public</p>
                  </div>
                  <p className="text-[10px] text-[var(--text-secondary)]">Anyone can see</p>
                </button>
                <button
                  onClick={() => setRepoVisibility("private")}
                  disabled={isCreating}
                  className={cn(
                    "p-3 rounded-lg border-2 transition-all duration-200 text-left disabled:opacity-50",
                    repoVisibility === "private"
                      ? "border-primary bg-primary/5"
                      : "border-[var(--border-color)] hover:border-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]/50"
                  )}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Lock className={cn(
                      "h-3.5 w-3.5",
                      repoVisibility === "private" ? "text-primary" : "text-[var(--text-secondary)]"
                    )} />
                    <p className="text-xs font-medium text-[var(--text-primary)]">Private</p>
                  </div>
                  <p className="text-[10px] text-[var(--text-secondary)]">Only you can see</p>
                </button>
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-6">
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} className="text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]">
              Cancel
            </Button>
            <Button size="sm" onClick={handleCreateProject} disabled={isCreating || !backendRepoName.trim()} className="text-xs bg-primary hover:bg-primary-hover text-primary-foreground shadow-sm disabled:opacity-50">
              {isCreating ? (
                <>
                  <Spinner className="h-3.5 w-3.5 mr-2" />
                  Creating...
                </>
              ) : (
                <>
                  <Github className="h-3.5 w-3.5 mr-2" />
                  Create Repository
                </>
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <LinkGitHubDialog open={showLinkDialog} onOpenChange={setShowLinkDialog} />
    </>
  );
}

// ============================================================================
// GitHub auth dialog (used for sign-in or connect)
// ============================================================================
export function LinkGitHubDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [isLinking, setIsLinking] = useState(false);
  const [linkError, setLinkError] = useState<string | null>(null);
  const { theme } = useTheme();

  const handleLinkGitHub = async () => {
    setIsLinking(true);
    setLinkError(null);
    try {
      // Fetch the OAuth URL from the backend, then redirect
      // credentials: "include" sends the access_token cookie so backend knows this is a "connect" operation
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const response = await fetch(`${API_URL}/api/auth/github`, {
        credentials: "include",  // Important: sends cookies so backend knows user is logged in
      });
      const data = await response.json().catch(() => ({}));
      
      if (data.auth_url) {
        window.location.href = data.auth_url;
      } else {
        console.error("No auth_url returned from GitHub OAuth endpoint", data);
        setLinkError(
          data.reason || data.detail || "GitHub sign-in is not available. Is the control API running the latest auth routes?"
        );
        setIsLinking(false);
      }
    } catch (error) {
      console.error("Failed to initiate GitHub OAuth:", error);
      setLinkError("Could not reach the GitHub sign-in endpoint.");
      setIsLinking(false);
    }
  };

  const features = [
    { icon: GitBranch, title: "Clone & Review", desc: "Read your code, sync repos, and plan deployments" },
    { icon: BellRing, title: "Real-time Sync", desc: "Get notified on push and PR events" },
    { icon: KeyRound, title: "Secure Access", desc: "Scoped permissions, revoke anytime" },
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md bg-[var(--bg-primary)] border-[var(--border-color)]">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-2">
            <div className={cn(
              "h-12 w-12 rounded-xl flex items-center justify-center",
              theme === "dark" ? "bg-[var(--bg-tertiary)]" : "bg-gray-900"
            )}>
              <Github className={cn("h-6 w-6", theme === "dark" ? "text-white" : "text-white")} />
            </div>
            <div>
              <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">Continue with GitHub</DialogTitle>
              <DialogDescription className="text-xs text-[var(--text-secondary)]">
                Sign in or connect GitHub to import and sync repositories
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 mt-4">
          {/* Features */}
          <div className="space-y-3">
            {features.map((feature, i) => (
              <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-[var(--bg-secondary)]/50 border border-[var(--border-color)]">
                <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <feature.icon className="h-4 w-4 text-primary" />
                </div>
                <div>
                  <p className="text-xs font-medium text-[var(--text-primary)]">{feature.title}</p>
                  <p className="text-[10px] text-[var(--text-secondary)]">{feature.desc}</p>
                </div>
              </div>
            ))}
          </div>

          {/* Permissions note - amber/yellow like verification banner */}
          <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
            <p className="text-[10px] text-amber-700 dark:text-amber-300 leading-relaxed">
              <strong>Permissions requested:</strong> Read access to code and metadata. 
              You can revoke access anytime from GitHub settings.
            </p>
          </div>
          {linkError ? (
            <p className="text-[10px] text-red-600 dark:text-red-400 leading-relaxed">{linkError}</p>
          ) : null}
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <Button 
            variant="outline" 
            size="sm" 
            onClick={() => onOpenChange(false)} 
            className="text-xs border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
          >
            Cancel
          </Button>
          <Button 
            size="sm" 
            onClick={handleLinkGitHub}
            disabled={isLinking}
            className="text-xs bg-primary hover:bg-primary-hover text-primary-foreground shadow-sm disabled:opacity-50"
          >
            {isLinking ? (
              <>
                <Spinner className="h-3.5 w-3.5 mr-2" />
                <span className="shimmer-text">Connecting</span>
              </>
            ) : (
              <>
                <Github className="h-3.5 w-3.5 mr-2" />
                Continue with GitHub
                <ExternalLink className="h-3 w-3 ml-1.5 opacity-60" />
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================================
// GitHub Repo type for API response
// ============================================================================
interface GitHubRepo {
  id: number;
  name: string;
  full_name: string;
  private: boolean;
  language: string | null;
  stargazers_count: number;
  updated_at: string;
  html_url: string;
}

type SourceRepoType = "backend" | "frontend";
type ImportStrategy = "use_as_backend" | "create_backend_repo";

/** Temporary: hide monorepo folder picker ("Backend entry point"); import always uses repo root. */
const SHOW_BACKEND_FOLDER_BROWSER = false;

/** When false, only "use this repo as backend" — hide "create new backend repo" (separate GitHub repo flow). */
const SHOW_CREATE_BACKEND_REPO_IMPORT_OPTION = false;

// ============================================================================
// GitHub Import Dialog
// ============================================================================
export function GitHubImportDialog({ 
  open, 
  onOpenChange,
  onProjectCreated,
  onGoToProject,
  defaultSourceRepoType = "backend",
}: { 
  open: boolean; 
  onOpenChange: (open: boolean) => void;
  onProjectCreated?: () => void;
  onGoToProject?: (project: { id: string; name: string; status: string }) => void;
  defaultSourceRepoType?: SourceRepoType;
}) {
  const { user, isAuthenticated } = useAuth();
  const [selectedRepo, setSelectedRepo] = useState<number | null>(null);
  const [backendFolderPath, setBackendFolderPath] = useState("");
  const [currentPath, setCurrentPath] = useState<string[]>([]); // Path segments for navigation
  const [folders, setFolders] = useState<string[]>([]);
  const [isLoadingFolders, setIsLoadingFolders] = useState(false);
  const [foldersFetchError, setFoldersFetchError] = useState<string | null>(null);
  const [foldersFetchRetryKey, setFoldersFetchRetryKey] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [showLinkDialog, setShowLinkDialog] = useState(false);
  const [showBackendRepoDialog, setShowBackendRepoDialog] = useState(false);
  const [savedSourceRepo, setSavedSourceRepo] = useState<{
    name: string; fullName: string; language?: string; private?: boolean; backendFolderPath?: string;
  } | undefined>(undefined);
  const [realRepos, setRealRepos] = useState<GitHubRepo[]>([]);
  const [isLoadingRepos, setIsLoadingRepos] = useState(false);
  const [repoError, setRepoError] = useState<string | null>(null);

  // Check if user has GitHub App installed (for repo access)
  // Note: github_id/github_username is just OAuth login, github_app_installed means we can access repos
  const isGitHubLinked = user?.github_app_installed ?? false;

  // Demo mode: show mock repos when not signed in
  const isDemoMode = !isAuthenticated;

  // Fetch real repos when dialog opens and user is authenticated with GitHub linked
  React.useEffect(() => {
    if (open && isAuthenticated && isGitHubLinked) {
      const fetchRepos = async () => {
        setIsLoadingRepos(true);
        setRepoError(null);
        try {
          const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
          const response = await fetch(`${API_URL}/api/github/repos`, {
            credentials: "include",
          });
          
          if (!response.ok) {
            throw new Error(`Failed to fetch repositories (${response.status})`);
          }
          
          const data = await response.json();
          setRealRepos(data);
        } catch (error) {
          console.error("Failed to fetch repos:", error);
          setRepoError("Failed to load repositories. Please try again.");
        } finally {
          setIsLoadingRepos(false);
        }
      };
      
      fetchRepos();
    }
  }, [open, isAuthenticated, isGitHubLinked]);

  // Reset state when repo selection changes
  React.useEffect(() => {
    if (!selectedRepo) {
      setFolders([]);
      setBackendFolderPath("");
      setCurrentPath([]);
      setFoldersFetchError(null);
      setFoldersFetchRetryKey(0);
    } else {
      // Reset to root when selecting a new repo (keep entry point in sync with breadcrumb)
      setCurrentPath([]);
      setBackendFolderPath("");
      setFoldersFetchError(null);
      setFoldersFetchRetryKey(0);
    }
  }, [selectedRepo]);

  // Fetch folders at current path level (GitHub API; no fake folder lists on failure)
  React.useEffect(() => {
    if (!SHOW_BACKEND_FOLDER_BROWSER) {
      setFolders([]);
      setFoldersFetchError(null);
      setIsLoadingFolders(false);
      return;
    }
    if (!selectedRepo) return;

    const reposToCheck = isDemoMode
      ? mockGitHubRepos.map(repo => ({
          id: repo.id,
          name: repo.name,
          fullName: repo.full_name,
          language: repo.language || "Unknown",
          stars: repo.stars,
          updated: repo.updated,
          private: repo.private,
        }))
      : realRepos.map(repo => ({
          id: repo.id,
          name: repo.name,
          fullName: repo.full_name,
          language: repo.language || "Unknown",
          stars: repo.stargazers_count,
          updated: new Date(repo.updated_at).toLocaleDateString(),
          private: repo.private,
        }));

    const selectedRepoDetails = reposToCheck.find(repo => repo.id === selectedRepo);
    if (!selectedRepoDetails) return;

    const currentPathStr = currentPath.join('/');
    const controller = new AbortController();

    if (isDemoMode) {
      setIsLoadingFolders(true);
      setFoldersFetchError(null);
      const timer = window.setTimeout(() => {
        if (controller.signal.aborted) return;
        if (currentPath.length === 0) {
          setFolders(['backend', 'frontend', 'apps', 'packages', 'src', 'docs']);
        } else if (currentPath[0] === 'apps') {
          setFolders(['api', 'web', 'mobile']);
        } else if (currentPath[0] === 'packages') {
          setFolders(['backend', 'frontend', 'shared']);
        } else if (currentPath[0] === 'src') {
          setFolders(['server', 'client', 'shared']);
        } else {
          setFolders([]);
        }
        setIsLoadingFolders(false);
      }, 300);
      return () => {
        controller.abort();
        window.clearTimeout(timer);
      };
    }

    const fetchFoldersAtPath = async (path: string) => {
      setIsLoadingFolders(true);
      setFoldersFetchError(null);
      try {
        const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        const [owner, repo] = selectedRepoDetails.fullName.split('/');
        if (!owner || !repo) {
          setFolders([]);
          setFoldersFetchError("Invalid repository name.");
          return;
        }
        const pathParam = path ? `path=${encodeURIComponent(path)}` : '';
        const queryString = pathParam ? `?${pathParam}` : '';
        const response = await fetch(
          `${API_URL}/api/github/repos/${owner}/${repo}/files${queryString}`,
          { credentials: "include", signal: controller.signal }
        );

        if (controller.signal.aborted) return;

        if (response.ok) {
          const data = await response.json();
          const directories = data
            .filter((item: { type?: string }) => item.type === 'dir')
            .map((item: { name: string }) => item.name)
            .sort();
          setFolders(directories);
          setFoldersFetchError(null);
          return;
        }

        let message = `Could not load folders (${response.status})`;
        try {
          const errBody = await response.json();
          if (typeof errBody?.detail === 'string') {
            message = errBody.detail;
          } else if (Array.isArray(errBody?.detail) && errBody.detail[0]?.msg) {
            message = errBody.detail[0].msg;
          }
        } catch {
          /* ignore */
        }
        setFolders([]);
        setFoldersFetchError(message);
      } catch (error) {
        if ((error as Error).name === 'AbortError') return;
        console.error("Failed to fetch folders:", error);
        setFolders([]);
        setFoldersFetchError("Could not load repository folders. Check your connection and try again.");
      } finally {
        if (!controller.signal.aborted) {
          setIsLoadingFolders(false);
        }
      }
    };

    fetchFoldersAtPath(currentPathStr);
    return () => controller.abort();
  }, [currentPath.join('/'), selectedRepo, isDemoMode, realRepos, foldersFetchRetryKey]);

  // Reset state when dialog closes
  React.useEffect(() => {
    if (!open) {
      setSelectedRepo(null);
      setBackendFolderPath("");
      setCurrentPath([]);
      setFolders([]);
      setSearchQuery("");
      setIsLoadingFolders(false);
      setFoldersFetchError(null);
      setFoldersFetchRetryKey(0);
    }
  }, [open]);

  /** Entry point always matches the folder you're viewing — avoids teal vs breadcrumb mismatch. */
  const goToPathDepth = (depth: number) => {
    const next = currentPath.slice(0, depth);
    setCurrentPath(next);
    setBackendFolderPath(next.join('/'));
  };

  const handleFolderClick = (folderName: string) => {
    const next = [...currentPath, folderName];
    setCurrentPath(next);
    setBackendFolderPath(next.join('/'));
  };

  // Use real repos when authenticated, mock repos for demo mode
  // Normalize both to have consistent property names
  const reposToShow = isDemoMode 
    ? mockGitHubRepos.map(repo => ({
        id: repo.id,
        name: repo.name,
        fullName: repo.full_name,  // Normalize from full_name to fullName
        language: repo.language || "Unknown",
        stars: repo.stars,
        updated: repo.updated,
        private: repo.private,
      }))
    : realRepos.map(repo => ({
        id: repo.id,
        name: repo.name,
        fullName: repo.full_name,  // Keep full name for API calls
        language: repo.language || "Unknown",
        stars: repo.stargazers_count,
        updated: new Date(repo.updated_at).toLocaleDateString(),
        private: repo.private,
      }));

  const filteredRepos = reposToShow.filter(repo =>
    repo.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Get selected repo details
  const selectedRepoDetails = reposToShow.find(repo => repo.id === selectedRepo);
  const isFrontendBeta = defaultSourceRepoType === "frontend";

  // Demo projects available for live demo
  const liveDemoProjects = [
    "ecommerce-clone",  // E-commerce: products, cart, orders
    "netflix-clone",    // Media: streaming, profiles
    "twitter-clone",    // Social: posts, follows, likes
    "notion-clone",     // Productivity: docs, collaboration
  ];
  
  // Pre-recorded demo projects (fallback if live fails)
  const preRecordedDemoProjects = ["ecommerce-clone"];

  // Handle import click - open project details / setup flow
  const handleImportClick = () => {
    if (!selectedRepo) return;

    const details = reposToShow.find(repo => repo.id === selectedRepo);
    if (details) {
      setSavedSourceRepo({
        name: details.name,
        fullName: details.fullName || details.name,
        language: details.language ?? undefined,
        private: details.private,
        backendFolderPath: backendFolderPath || undefined,
      });
    }

    setShowBackendRepoDialog(true);
    onOpenChange(false);
  };

  // If dialog opens, user is signed in, but GitHub not linked → show link dialog
  React.useEffect(() => {
    if (open && isAuthenticated && !isGitHubLinked) {
      setShowLinkDialog(true);
      onOpenChange(false);
    }
  }, [open, isAuthenticated, isGitHubLinked, onOpenChange]);

  // Determine if we should show the repo picker
  // Show if: demo mode OR (authenticated AND GitHub linked)
  const shouldShowRepoPicker = isDemoMode || (isAuthenticated && isGitHubLinked);

  return (
    <>
      <Dialog open={open && shouldShowRepoPicker} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg bg-[var(--bg-primary)] border-[var(--border-color)] flex flex-col max-h-[min(90dvh,40rem)] gap-0 overflow-hidden p-0">
        <div className="shrink-0 px-6 pt-6 pb-3 space-y-3 border-b border-[var(--border-color)]">
          <DialogHeader className="space-y-0">
            <div className="flex items-center gap-3">
              <div className={cn(
                "h-10 w-10 rounded-xl flex items-center justify-center shrink-0",
                isDemoMode 
                  ? "bg-[var(--bg-tertiary)]" 
                  : "bg-[#10b981]/10 border border-[#10b981]/30"
              )}>
                <Github className={cn("h-5 w-5", isDemoMode ? "text-[var(--text-primary)]" : "text-[#10b981]")} />
              </div>
              <div className="min-w-0">
                <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">
                  {isFrontendBeta ? "Import Frontend Repository" : "Import Project"}
                </DialogTitle>
                <DialogDescription className="text-xs text-[var(--text-secondary)]">
                  {isDemoMode ? (
                    <span>Preview mode - <span className="text-amber-500">sign in to import real repos</span></span>
                  ) : (
                    <>Connected as <span className="text-[#10b981] font-medium">@{user?.github_username}</span></>
                  )}
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>

          {/* Mode banner (frontend beta only) */}
          {isFrontendBeta && (
            <div className="p-2.5 rounded-lg border bg-amber-500/10 border-amber-500/20">
              <p className="text-[10px] leading-relaxed text-amber-700 dark:text-amber-300">
                <strong>Beta:</strong> Import a frontend repo to infer contracts and generate a matching backend plan.
              </p>
            </div>
          )}

          {/* Demo mode banner */}
          {isDemoMode && (
            <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20">
              <p className="text-[10px] text-amber-700 dark:text-amber-300 leading-relaxed">
                <strong>Demo Mode:</strong> These are sample repositories. Sign in to import your own GitHub repos.
              </p>
            </div>
          )}
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-6 py-3">
          {/* Note: Demo projects like ecommerce-clone are in mockGitHubRepos.
              When imported, they trigger the demo flow automatically. */}

          <div className="space-y-4">
            <div className="relative">
              <Input
                placeholder="Search repositories..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-10 text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] pl-9 focus:border-primary focus:ring-primary/20"
              />
              <Globe className="absolute left-3 top-3 h-4 w-4 text-[var(--text-secondary)]" />
            </div>

            <div className="max-h-64 overflow-y-auto space-y-1 border border-[var(--border-color)] rounded-xl p-1.5 bg-[var(--bg-secondary)]/30">
              {isLoadingRepos ? (
                <div className="py-8 text-center">
                  <Loader2 className="h-5 w-5 animate-spin mx-auto text-primary mb-2" />
                  <p className="text-xs shimmer-text">Loading repositories</p>
                </div>
              ) : repoError ? (
                <div className="py-8 text-center">
                  <p className="text-xs text-red-500 mb-2">{repoError}</p>
                  <Button 
                    size="sm" 
                    variant="outline" 
                    onClick={() => {
                      setRepoError(null);
                      // Trigger re-fetch by toggling a state or calling fetch again
                      setIsLoadingRepos(true);
                      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
                      fetch(`${API_URL}/api/github/repos`, { credentials: "include" })
                        .then(res => res.json())
                        .then(data => setRealRepos(data))
                        .catch(() => setRepoError("Failed to load repositories"))
                        .finally(() => setIsLoadingRepos(false));
                    }}
                    className="text-xs"
                  >
                    Try Again
                  </Button>
                </div>
              ) : filteredRepos.length === 0 ? (
                <div className="py-8 text-center">
                  <p className="text-xs text-[var(--text-secondary)]">No repositories found</p>
                </div>
              ) : (
                filteredRepos.map((repo) => {
                  return (
                <button
                  key={repo.id}
                  onClick={() => setSelectedRepo(repo.id)}
                  className={cn(
                    "w-full flex items-center gap-3 p-3 rounded-lg transition-all duration-200 text-left",
                    selectedRepo === repo.id
                      ? "bg-primary/10 border-2 border-primary"
                      : "hover:bg-[var(--bg-tertiary)] border-2 border-transparent"
                  )}
                >
                  <div className={cn(
                    "h-9 w-9 rounded-lg flex items-center justify-center",
                    selectedRepo === repo.id ? "bg-primary/20" : "bg-[var(--bg-tertiary)]"
                  )}>
                    {repo.private ? (
                      <Lock className={cn("h-4 w-4", selectedRepo === repo.id ? "text-primary" : "text-[var(--text-secondary)]")} />
                    ) : (
                      <Globe className={cn("h-4 w-4", selectedRepo === repo.id ? "text-primary" : "text-[var(--text-secondary)]")} />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className={cn(
                        "text-xs font-medium truncate",
                        selectedRepo === repo.id ? "text-primary" : "text-[var(--text-primary)]"
                      )}>{repo.name}</p>
                      {repo.private && <Lock className="h-3 w-3 text-[var(--text-secondary)]" />}
                    </div>
                    <div className="flex items-center gap-3 text-[10px] text-[var(--text-secondary)]">
                      <span className="flex items-center gap-1">
                        <span className="h-2 w-2 rounded-full bg-blue-500" />
                        {repo.language}
                      </span>
                      <span className="flex items-center gap-1">
                        <Star className="h-3 w-3" />
                        {repo.stars}
                      </span>
                      <span>{repo.updated}</span>
                    </div>
                  </div>
                  {selectedRepo === repo.id && <Check className="h-4 w-4 text-primary" />}
                </button>
                  );
                })
              )}
            </div>

            {/* Backend folder browser - shown when repo is selected */}
            {selectedRepo && SHOW_BACKEND_FOLDER_BROWSER && (
              <div className="mt-3 space-y-2">
                <Label className="text-xs text-[var(--text-secondary)]">
                  Backend entry point
                </Label>

                {/* Breadcrumb = analysis path; horizontal scroll when deeply nested */}
                <div className="flex flex-nowrap items-center gap-1 text-xs min-h-[28px] max-w-full overflow-x-auto overflow-y-hidden py-0.5 [scrollbar-width:thin]">
                  <button
                    type="button"
                    onClick={() => goToPathDepth(0)}
                    className={cn(
                      "shrink-0 rounded px-1.5 py-0.5 transition-colors",
                      currentPath.length === 0
                        ? "bg-primary/15 text-primary"
                        : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                    )}
                  >
                    /
                  </button>
                  {currentPath.map((segment, index) => {
                    const isActiveTail = index === currentPath.length - 1;
                    return (
                      <React.Fragment key={`${segment}-${index}`}>
                        <ChevronRight className="h-3 w-3 shrink-0 text-[var(--text-secondary)]" />
                        <button
                          type="button"
                          onClick={() => goToPathDepth(index + 1)}
                          className={cn(
                            "shrink-0 rounded px-1.5 py-0.5 transition-colors max-w-[10rem] truncate",
                            isActiveTail
                              ? "bg-primary/15 text-primary"
                              : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
                          )}
                          title={segment}
                        >
                          {segment}
                        </button>
                      </React.Fragment>
                    );
                  })}
                </div>

                {/* Folder list */}
                {isLoadingFolders ? (
                  <div className="h-32 rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)] flex items-center justify-center">
                    <Spinner className="h-4 w-4 text-[var(--text-secondary)]" />
                  </div>
                ) : foldersFetchError ? (
                  <div className="rounded-lg border border-red-500/30 bg-[var(--bg-secondary)] px-3 py-4 space-y-2">
                    <p className="text-xs text-red-600 dark:text-red-400">{foldersFetchError}</p>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="text-xs h-8"
                      onClick={() => setFoldersFetchRetryKey((k) => k + 1)}
                    >
                      Retry
                    </Button>
                  </div>
                ) : (
                  <div className="rounded-lg border border-[var(--border-color)] bg-[var(--bg-secondary)] max-h-48 overflow-y-auto">
                    {/* Folder list */}
                    {folders.length > 0 ? (
                      folders.map((folder) => (
                        <button
                          key={folder}
                          onClick={() => handleFolderClick(folder)}
                          className="w-full flex items-center gap-2 px-3 py-2 text-xs text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
                        >
                          <FolderOpen className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
                          <span>{folder}/</span>
                          <ChevronRight className="h-3 w-3 text-[var(--text-secondary)] ml-auto" />
                        </button>
                      ))
                    ) : (
                      <div className="px-3 py-6 text-center text-xs text-[var(--text-secondary)]">
                        No subfolders found
                      </div>
                    )}
                  </div>
                )}

                <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
                  {backendFolderPath
                    ? `We'll analyze the code starting from ${backendFolderPath}/`
                    : "We'll analyze the entire repository from the root"}
                </p>
              </div>
            )}
          </div>
        </div>

        <div className="shrink-0 flex justify-end gap-2 px-6 py-4 border-t border-[var(--border-color)] bg-[var(--bg-primary)]">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} className="text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors">Cancel</Button>
          <Button
            size="sm"
            disabled={!selectedRepo}
            onClick={handleImportClick}
            className="bg-primary hover:bg-primary-hover text-primary-foreground text-xs shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isDemoMode ? "Continue (Demo)" : "Continue"}
          </Button>
        </div>
        </DialogContent>
      </Dialog>

      {/* Link GitHub Dialog - shown when signed in but GitHub not connected */}
      <LinkGitHubDialog open={showLinkDialog} onOpenChange={setShowLinkDialog} />

      {/* Project Details Dialog - shown after selecting source repo */}
      <ProjectDetailsDialog
        open={showBackendRepoDialog}
        onOpenChange={setShowBackendRepoDialog}
        onProjectCreated={onProjectCreated}
        onGoToProject={onGoToProject}
        sourceRepo={savedSourceRepo}
        isDemoMode={isDemoMode}
        defaultSourceRepoType={defaultSourceRepoType}
      />
    </>
  );
}

// ============================================================================
// Add Repository Dialog — lightweight picker to link a repo to existing project
// ============================================================================
export function AddRepositoryDialog({
  open,
  onOpenChange,
  projectId,
  projectName,
  onRepositoryAdded,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  projectName: string;
  onRepositoryAdded?: () => void;
}) {
  const { user, isAuthenticated } = useAuth();
  const [repos, setRepos] = useState<GitHubRepo[]>([]);
  const [isLoadingRepos, setIsLoadingRepos] = useState(false);
  const [repoError, setRepoError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedRepoId, setSelectedRepoId] = useState<number | null>(null);
  const [isAdding, setIsAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  React.useEffect(() => {
    if (!open) return;
    setSearchQuery("");
    setSelectedRepoId(null);
    setAddError(null);

    const fetchRepos = async () => {
      setIsLoadingRepos(true);
      setRepoError(null);
      try {
        const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        const res = await fetch(`${API_URL}/api/github/repos`, { credentials: "include" });
        if (!res.ok) throw new Error("Failed to fetch repositories");
        setRepos(await res.json());
      } catch {
        setRepoError("Failed to load repositories. Please try again.");
      } finally {
        setIsLoadingRepos(false);
      }
    };
    if (isAuthenticated) fetchRepos();
  }, [open, isAuthenticated]);

  const reposNormalized = repos.map((repo) => ({
    id: repo.id,
    name: repo.name,
    fullName: repo.full_name,
    language: repo.language || "Unknown",
    stars: repo.stargazers_count,
    updated: new Date(repo.updated_at).toLocaleDateString(),
    private: repo.private,
  }));

  const filteredRepos = reposNormalized.filter((r) =>
    r.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleAdd = async () => {
    const selected = reposNormalized.find((r) => r.id === selectedRepoId);
    if (!selected) return;
    setIsAdding(true);
    setAddError(null);
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${API_URL}/api/projects/${projectId}/repositories`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ github_repo_full_name: selected.fullName }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `Failed to add repository (${res.status})`);
      }
      onOpenChange(false);
      onRepositoryAdded?.();
    } catch (e: any) {
      setAddError(e.message);
    } finally {
      setIsAdding(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg bg-[var(--bg-primary)] border-[var(--border-color)] flex flex-col max-h-[min(90dvh,40rem)] gap-0 overflow-hidden p-0">
        <div className="shrink-0 px-6 pt-6 pb-3 space-y-3 border-b border-[var(--border-color)]">
          <DialogHeader className="space-y-0">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-xl flex items-center justify-center shrink-0 bg-[#10b981]/10 border border-[#10b981]/30">
                <Github className="h-5 w-5 text-[#10b981]" />
              </div>
              <div className="min-w-0">
                <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">
                  Add Repository
                </DialogTitle>
                <DialogDescription className="text-xs text-[var(--text-secondary)]">
                  Connected as <span className="text-[#10b981] font-medium">@{user?.github_username}</span>
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-6 py-3">
          <div className="space-y-4">
            <div className="relative">
              <Input
                placeholder="Search repositories..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-10 text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] pl-9 focus:border-primary focus:ring-primary/20"
              />
              <Globe className="absolute left-3 top-3 h-4 w-4 text-[var(--text-secondary)]" />
            </div>

            <div className="max-h-64 overflow-y-auto space-y-1 border border-[var(--border-color)] rounded-xl p-1.5 bg-[var(--bg-secondary)]/30">
              {isLoadingRepos ? (
                <div className="py-8 text-center">
                  <Loader2 className="h-5 w-5 animate-spin mx-auto text-primary mb-2" />
                  <p className="text-xs shimmer-text">Loading repositories</p>
                </div>
              ) : repoError ? (
                <div className="py-8 text-center">
                  <p className="text-xs text-red-500 mb-2">{repoError}</p>
                  <Button size="sm" variant="outline" onClick={() => {
                    setRepoError(null);
                    setIsLoadingRepos(true);
                    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
                    fetch(`${API_URL}/api/github/repos`, { credentials: "include" })
                      .then((r) => r.json())
                      .then(setRepos)
                      .catch(() => setRepoError("Failed to load repositories"))
                      .finally(() => setIsLoadingRepos(false));
                  }} className="text-xs">Try Again</Button>
                </div>
              ) : filteredRepos.length === 0 ? (
                <div className="py-8 text-center">
                  <p className="text-xs text-[var(--text-secondary)]">No repositories found</p>
                </div>
              ) : (
                filteredRepos.map((repo) => (
                  <button
                    key={repo.id}
                    onClick={() => setSelectedRepoId(repo.id)}
                    className={cn(
                      "w-full flex items-center gap-3 p-3 rounded-lg transition-all duration-200 text-left",
                      selectedRepoId === repo.id
                        ? "bg-primary/10 border-2 border-primary"
                        : "hover:bg-[var(--bg-tertiary)] border-2 border-transparent"
                    )}
                  >
                    <div className={cn(
                      "h-9 w-9 rounded-lg flex items-center justify-center",
                      selectedRepoId === repo.id ? "bg-primary/20" : "bg-[var(--bg-tertiary)]"
                    )}>
                      {repo.private ? (
                        <Lock className={cn("h-4 w-4", selectedRepoId === repo.id ? "text-primary" : "text-[var(--text-secondary)]")} />
                      ) : (
                        <Globe className={cn("h-4 w-4", selectedRepoId === repo.id ? "text-primary" : "text-[var(--text-secondary)]")} />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className={cn(
                          "text-xs font-medium truncate",
                          selectedRepoId === repo.id ? "text-primary" : "text-[var(--text-primary)]"
                        )}>{repo.name}</p>
                        {repo.private && <Lock className="h-3 w-3 text-[var(--text-secondary)]" />}
                      </div>
                      <div className="flex items-center gap-3 text-[10px] text-[var(--text-secondary)]">
                        <span className="flex items-center gap-1">
                          <span className="h-2 w-2 rounded-full bg-blue-500" />
                          {repo.language}
                        </span>
                        <span className="flex items-center gap-1">
                          <Star className="h-3 w-3" />
                          {repo.stars}
                        </span>
                        <span>{repo.updated}</span>
                      </div>
                    </div>
                    {selectedRepoId === repo.id && <Check className="h-4 w-4 text-primary" />}
                  </button>
                ))
              )}
            </div>

            {addError && (
              <p className="text-xs text-red-500">{addError}</p>
            )}
          </div>
        </div>

        <div className="shrink-0 flex justify-end gap-2 px-6 py-4 border-t border-[var(--border-color)] bg-[var(--bg-primary)]">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} className="text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors">
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!selectedRepoId || isAdding}
            onClick={handleAdd}
            className="bg-primary hover:bg-primary-hover text-primary-foreground text-xs shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isAdding ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin mr-1.5" />
                Adding...
              </>
            ) : (
              "Add Repository"
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}


// ============================================================================
// Project Details Dialog - Step 1: Confirm project name
// ============================================================================
export function ProjectDetailsDialog({
  open,
  onOpenChange,
  onProjectCreated,
  onGoToProject,
  sourceRepo,
  isDemoMode = false,
  defaultSourceRepoType = "backend",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onProjectCreated?: () => void;
  onGoToProject?: (project: { id: string; name: string; status: string }) => void;
  sourceRepo?: {
    name: string;
    fullName: string;
    language?: string;
    private?: boolean;
    backendFolderPath?: string;
  };
  isDemoMode?: boolean;
  defaultSourceRepoType?: SourceRepoType;
}) {
  const [projectName, setProjectName] = useState("");
  const [projectId, setProjectId] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdProject, setCreatedProject] = useState<{ id: string; name: string; status?: string } | null>(null);
  const [importStrategy, setImportStrategy] = useState<ImportStrategy>("use_as_backend");

  // Initialize values when dialog opens
  React.useEffect(() => {
    if (open && sourceRepo) {
      const name = sourceRepo.name;
      setProjectName(name);
      setProjectId(`proj-${crypto.randomUUID().substring(0, 8)}`);
      setError(null);
      setCreatedProject(null);
      setImportStrategy("use_as_backend");
    }
  }, [open, sourceRepo, defaultSourceRepoType]);

  const handleNameChange = (newName: string) => {
    setProjectName(newName);
  };

  const handleSaveChanges = async () => {
    if (!sourceRepo) return;

    if (isDemoMode) {
      setIsSaving(true);
      await new Promise(resolve => setTimeout(resolve, 1000));
      setIsSaving(false);
      const demoProject = { id: projectId, name: projectName, status: "draft" };
      setCreatedProject(demoProject);
      onOpenChange(false);
      if (onGoToProject) onGoToProject(demoProject);
      return;
    }

    setIsSaving(true);
    setError(null);

    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const createResponse = await fetch(`${API_URL}/api/projects/`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: projectName,
        }),
      });

      if (!createResponse.ok) {
        const err = await createResponse.json();
        throw new Error(err.detail || "Failed to create project");
      }

      const project = await createResponse.json();
      console.log("Created project:", project);

      if (importStrategy === "use_as_backend") {
        const workspaceResponse = await fetch(
          `${API_URL}/api/projects/${project.id}/workspaces/import-repo`,
          {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              name: `${projectName} Workspace`,
              repo_url: `https://github.com/${sourceRepo.fullName}.git`,
              repo_branch: "main",
              workspace_path: sourceRepo.backendFolderPath?.replace(/^\/+|\/+$/g, "") || undefined,
              environment: "dev",
            }),
          }
        );

        if (!workspaceResponse.ok) {
          const err = await workspaceResponse.json();
          throw new Error(err.detail || "Failed to create backend workspace");
        }
      }
      
      setCreatedProject({ id: project.id, name: project.name, status: project.status || "draft" });
      if (onProjectCreated) {
        onProjectCreated();
      }
      onOpenChange(false);
      if (onGoToProject) {
        onGoToProject({
          id: project.id,
          name: project.name,
          status: project.status || "draft",
        });
      }

    } catch (err: any) {
      console.error("Error creating project:", err);
      setError(err.message || "Failed to create project");
    } finally {
      setIsSaving(false);
    }
  };

  const handleClose = () => {
    setProjectName("");
    setError(null);
    onOpenChange(false);
  };

  return (
    <>
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent className="max-w-md bg-[var(--bg-primary)] border-[var(--border-color)] flex flex-col max-h-[min(90dvh,40rem)] gap-0 overflow-hidden p-0">
          <div className="shrink-0 px-6 pt-6 pb-3 border-b border-[var(--border-color)]">
            <DialogHeader className="space-y-0">
              <div className="flex items-center gap-3">
                <div className={cn(
                  "h-10 w-10 rounded-xl flex items-center justify-center shrink-0",
                  "bg-primary/10 border border-primary/30"
                )}>
                  <PackagePlus className="h-5 w-5 text-primary" />
                </div>
                <div className="min-w-0">
                  <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">Create Project</DialogTitle>
                  <DialogDescription className="text-xs text-[var(--text-secondary)]">
                    Confirm your project details before continuing
                  </DialogDescription>
                </div>
              </div>
            </DialogHeader>
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-6 py-3">
          <div className="space-y-4">
            {/* Error message */}
            {error && (
              <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
              </div>
            )}

            {/* Source repo info */}
            {sourceRepo && (
              <div className="p-3 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-color)]">
                <div className="flex items-center gap-2 mb-1">
                  <Github className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
                  <span className="text-xs text-[var(--text-secondary)]">Source Repository</span>
                </div>
                <p className="text-sm font-medium text-[var(--text-primary)]">{sourceRepo.fullName}</p>
                <div className="flex items-center gap-2 mt-1">
                  {sourceRepo.language && (
                    <p className="text-[10px] text-[var(--text-secondary)]">{sourceRepo.language}</p>
                  )}
                  {sourceRepo.backendFolderPath && (
                    <>
                      {sourceRepo.language && <span className="text-[10px] text-[var(--text-secondary)]">•</span>}
                      <div className="flex items-center gap-1">
                        <FolderOpen className="h-2.5 w-2.5 text-[var(--text-secondary)]" />
                        <p className="text-[10px] text-[var(--text-secondary)]">{sourceRepo.backendFolderPath}</p>
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}

            {sourceRepo && (!SHOW_CREATE_BACKEND_REPO_IMPORT_OPTION || importStrategy === "use_as_backend") && (
              <div className="p-2.5 rounded-lg border bg-primary/10 border-primary/20">
                <p className="text-[10px] leading-relaxed text-primary dark:text-primary-soft">
                  We only <span className="underline underline-offset-2">read</span> your default branch (e.g.{" "}
                  <code className="rounded bg-[var(--bg-tertiary)] px-1 py-0 text-[9px]">origin/main</code>
                  ). Agent changes are pushed to a{" "}
                  <span className="underline underline-offset-2">separate branch</span> for pull request review.
                </p>
              </div>
            )}

            {/* Import strategy (optional second path: new backend repo) */}
            {SHOW_CREATE_BACKEND_REPO_IMPORT_OPTION && (
              <div className="grid gap-2">
                <Label className="text-xs text-[var(--text-secondary)]">How should we use this repo?</Label>
                <div className="grid gap-2">
                  {[
                    {
                      id: "use_as_backend" as const,
                      title: "Use this repo as backend",
                      desc: "Treat this codebase as the main backend you want to continue evolving.",
                    },
                    {
                      id: "create_backend_repo" as const,
                      title: "Create a new backend repo",
                      desc: "Use this repo as source context, but sync the backend to a new repo.",
                    },
                  ].map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => setImportStrategy(option.id)}
                      className={cn(
                        "rounded-lg border p-3 text-left transition-all",
                        importStrategy === option.id
                          ? "border-primary bg-primary/5"
                          : "border-[var(--border-color)] hover:bg-[var(--bg-secondary)]"
                      )}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-xs font-medium text-[var(--text-primary)]">{option.title}</p>
                      </div>
                      <p className="mt-1 text-[10px] text-[var(--text-secondary)]">{option.desc}</p>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Project Name */}
            <div className="grid gap-2">
              <Label className="text-xs text-[var(--text-secondary)]">Project Name</Label>
              <Input
                value={projectName}
                onChange={(e) => handleNameChange(e.target.value)}
                placeholder="My Awesome Project"
                disabled={isSaving}
                className="h-10 text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] focus:border-primary focus:ring-primary/20 disabled:opacity-50"
              />
            </div>
          </div>
          </div>

          <div className="shrink-0 flex justify-end gap-2 px-6 py-4 border-t border-[var(--border-color)] bg-[var(--bg-primary)]">
            <Button
              variant="outline"
              size="sm"
              onClick={handleClose}
              disabled={isSaving}
              className="text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors disabled:opacity-50"
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleSaveChanges}
              disabled={!projectName || isSaving}
              className="text-xs bg-primary hover:bg-primary-hover text-primary-foreground shadow-sm disabled:opacity-50"
            >
              {isSaving ? (
                <>
                  <Spinner className="h-3.5 w-3.5 mr-2" />
                  Creating...
                </>
              ) : (
                "Save & Continue"
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

    </>
  );
}

// ============================================================================
// Cloud Provider Selection Dialog - Step 2.5: Choose cloud provider
// ============================================================================
export function CloudProviderSelectionDialog({
  open,
  onOpenChange,
  onProviderSelected,
  currentProvider,
  isSaving = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onProviderSelected: (provider: "aws" | "gcp") => void;
  currentProvider?: "aws" | "gcp";
  isSaving?: boolean;
}) {
  const [selectedProvider, setSelectedProvider] = useState<"aws" | "gcp" | "azure" | null>(null);
  const { theme } = useTheme();

  React.useEffect(() => {
    if (open) {
      setSelectedProvider(currentProvider ?? null);
    }
  }, [open, currentProvider]);

  const providers = [
    {
      id: "aws" as const,
      name: "AWS",
      iconLight: "/aws-light.svg",
      iconDark: "/aws-dark.svg",
      subtitle: "Coming soon",
      available: false,
    },
    {
      id: "gcp" as const,
      name: "GCP",
      icon: "/google-cloud.svg",
      subtitle: "Hosted in your own cloud",
      available: true,
    },
    {
      id: "azure" as const,
      name: "Azure",
      icon: "/azure.svg",
      subtitle: "Coming soon",
      available: false,
    },
  ];

  const handleContinue = () => {
    if (selectedProvider && selectedProvider !== "azure" && selectedProvider !== "aws") {
      onProviderSelected(selectedProvider);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl bg-[var(--bg-primary)] border-[var(--border-color)]">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-3">
            <div className="h-10 w-10 rounded-xl bg-primary/10 border border-primary/30 flex items-center justify-center">
              <MonitorCloud className="h-5 w-5 text-primary" />
            </div>
            <div>
              <DialogTitle className="text-base font-semibold text-[var(--text-primary)]">Choose your cloud provider</DialogTitle>
              <DialogDescription className="text-[10px] text-[var(--text-secondary)] mt-1">
                We currently support GCP
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-5">
          {/* Info banner */}
          <div className="p-3 rounded-lg bg-primary/10 border border-primary/20 flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-primary mt-0.5 flex-shrink-0" />
            <p className="text-xs text-primary leading-relaxed">
              Select your existing cloud provider to get started.
            </p>
          </div>

          {/* Prompt */}
          <div>
            <Label className="text-sm text-[var(--text-secondary)] mb-3 block">
              Select your hosting backend:
            </Label>

            {/* Provider cards */}
            <div className="grid grid-cols-3 gap-4">
              {providers.map((provider) => (
                <button
                  key={provider.id}
                  onClick={() => provider.available && setSelectedProvider(provider.id)}
                  disabled={!provider.available}
                  className={cn(
                    "relative p-6 rounded-xl border-2 transition-all duration-200 text-center",
                    !provider.available && "opacity-40 cursor-not-allowed",
                    provider.available && selectedProvider === provider.id
                      ? "border-primary bg-primary/5 shadow-lg"
                      : provider.available
                      ? "border-[var(--border-color)] hover:border-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]/50"
                      : "border-[var(--border-color)]"
                  )}
                >
                  {/* Logo */}
                  <div className="mx-auto mb-4 flex items-center justify-center">
                    <img
                      src={
                        'iconLight' in provider && 'iconDark' in provider
                          ? theme === 'dark'
                            ? provider.iconDark
                            : provider.iconLight
                          : provider.icon
                      }
                      alt={provider.name}
                      className="h-8 w-8 object-contain"
                    />
                  </div>

                  {/* Name */}
                  <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1">
                    {provider.name}
                  </h3>

                  {/* Subtitle */}
                  <p className="text-xs text-[var(--text-secondary)]">
                    {provider.subtitle}
                  </p>

                  {/* Checkmark for selected */}
                  {provider.available && selectedProvider === provider.id && (
                    <div className="absolute top-2 left-2">
                      <Check className="h-4 w-4 text-primary" />
                    </div>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Warning banner */}
          <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-400 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-[12px] text-amber-600 dark:text-amber-400 leading-relaxed">
                  We currently don&apos;t support migration between cloud providers. If you want to rebuild your backend on another cloud, you&apos;ll need to create a new project.
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            disabled={isSaving}
            className="text-xs border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
          >
            Back
          </Button>
          <Button
            size="sm"
            onClick={handleContinue}
            disabled={!selectedProvider || selectedProvider === "azure" || isSaving}
            className="text-xs bg-primary hover:bg-primary-hover text-primary-foreground shadow-sm disabled:opacity-50"
          >
            {isSaving ? "Saving..." : "Continue"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================================
// Backend Repo Dialog - create or attach backend repository
// ============================================================================
export function CreateBackendRepoDialog({
  open,
  onOpenChange,
  project,
  frontendRepoName,
  isDemoMode = false,
  onProjectCreated,
  onGoToProject,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project?: { id: string; name: string; status?: string } | null;
  frontendRepoName?: string;
  isDemoMode?: boolean;
  onProjectCreated?: () => void;
  onGoToProject?: (project: { id: string; name: string; status: string }) => void;
}) {
  const [backendRepoName, setBackendRepoName] = useState("");
  const [repoVisibility, setRepoVisibility] = useState<"public" | "private">("private");
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [repoNameError, setRepoNameError] = useState<string | null>(null);
  const [repoNameChecking, setRepoNameChecking] = useState(false);
  const [repoNameAvailable, setRepoNameAvailable] = useState<boolean | null>(null);
  const [showCloudSelection, setShowCloudSelection] = useState(false);
  const [selectedCloudProvider, setSelectedCloudProvider] = useState<"aws" | "gcp" | null>(null);

  // Auto-suggest backend repo name based on the source repo
  React.useEffect(() => {
    if (open && frontendRepoName && !backendRepoName) {
      const suggestion = frontendRepoName.endsWith("-frontend")
        ? frontendRepoName.replace("-frontend", "-backend")
        : `${frontendRepoName}-backend`;
      setBackendRepoName(suggestion);
    }
  }, [open, frontendRepoName]);

  // Reset state when dialog opens
  React.useEffect(() => {
    if (open) {
      setError(null);
      setSuccess(false);
      setRepoNameError(null);
      setRepoNameAvailable(null);
      setShowCloudSelection(false);
      setSelectedCloudProvider(null);
    }
  }, [open]);

  // Debounced backend repo name validation (check if it exists on GitHub)
  React.useEffect(() => {
    if (!backendRepoName || isDemoMode) {
      setRepoNameError(null);
      setRepoNameAvailable(null);
      return;
    }

    // Basic validation
    if (backendRepoName.length < 2) {
      setRepoNameError("Repository name must be at least 2 characters");
      setRepoNameAvailable(false);
      return;
    }

    if (!/^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(backendRepoName)) {
      setRepoNameError("Repository name can only contain letters, numbers, hyphens, underscores, and periods");
      setRepoNameAvailable(false);
      return;
    }

    const timer = setTimeout(async () => {
      setRepoNameChecking(true);
      try {
        const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        const response = await fetch(`${API_URL}/api/github/check-repo-name`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ name: backendRepoName }),
        });

        if (response.ok) {
          const data = await response.json();
          if (!data.available) {
            setRepoNameError(data.suggestion 
              ? `Repository already exists. Try: ${data.suggestion}`
              : "Repository already exists"
            );
            setRepoNameAvailable(false);
          } else {
            setRepoNameError(null);
            setRepoNameAvailable(true);
          }
        }
      } catch (error) {
        console.error("Repo name check failed:", error);
        // Assume available on network error
        setRepoNameError(null);
        setRepoNameAvailable(true);
      } finally {
        setRepoNameChecking(false);
      }
    }, 400);

    return () => clearTimeout(timer);
  }, [backendRepoName, isDemoMode]);

  const handleCreateBackendRepo = async () => {
    if (isDemoMode) {
      setIsCreating(true);
      await new Promise(resolve => setTimeout(resolve, 1500));
      setIsCreating(false);
      // Show cloud provider selection instead of success
      setShowCloudSelection(true);
      onOpenChange(false); // Close backend repo dialog
      return;
    }

    if (!project?.id) {
      setError("No project found");
      return;
    }

    setIsCreating(true);
    setError(null);

    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

      const response = await fetch(`${API_URL}/api/projects/${project.id}/backend-repo`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: backendRepoName,
          private: repoVisibility === "private",
          description: `Backend for ${project.name}`,
        }),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Failed to create backend repository");
      }

      const backendRepo = await response.json();
      console.log("Created backend repo:", backendRepo);

      // Show cloud provider selection instead of success
      setShowCloudSelection(true);
      onOpenChange(false); // Close backend repo dialog

      // Refresh the project list
      if (onProjectCreated) {
        onProjectCreated();
      }

    } catch (err: any) {
      console.error("Error creating backend repo:", err);
      setError(err.message || "Failed to create backend repository");
    } finally {
      setIsCreating(false);
    }
  };

  const handleCloudProviderSelected = async (provider: "aws" | "gcp") => {
    setSelectedCloudProvider(provider);
    
    // For demo mode, trigger the live demo with the selected cloud provider
    if (isDemoMode && project?.id) {
      setShowCloudSelection(false);
      setSuccess(true);
      
      setTimeout(() => {
        window.dispatchEvent(new CustomEvent('demoImportLiveProject', { 
          detail: { 
            id: project.id, 
            cloudProvider: provider,
          } 
        }));
      }, 500);
      return;
    }
    
    if (project?.id) {
      try {
        const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        await fetch(`${API_URL}/api/projects/${project.id}/cloud-provider`, {
          method: "PATCH",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cloud_provider: provider }),
        });
        console.log(`Updated project ${project.id} cloud_provider to ${provider}`);
      } catch (err) {
        console.error("Failed to update cloud provider:", err);
      }
    }
    
    setShowCloudSelection(false);
    setSuccess(true); // Now show success screen
  };

  const handleClose = () => {
    // If success, trigger onGoToProject to set the current project
    if (success && project && onGoToProject) {
      onGoToProject({
        id: project.id,
        name: project.name,
        status: project.status || "draft",
      });
    }
    
    setBackendRepoName("");
    setError(null);
    setSuccess(false);
    onOpenChange(false);
  };

  return (
    <>
      <CloudProviderSelectionDialog
        open={showCloudSelection}
        onOpenChange={setShowCloudSelection}
        onProviderSelected={handleCloudProviderSelected}
      />

      <Dialog open={open || success} onOpenChange={handleClose}>
        <DialogContent className="max-w-md bg-[var(--bg-primary)] border-[var(--border-color)]">
          {success ? (
          // Success state
          <>
            <DialogHeader>
              <div className="flex items-center gap-3 mb-2">
                <div className="h-10 w-10 rounded-xl flex items-center justify-center bg-[#10b981]/10 border border-[#10b981]/30">
                  <Check className="h-5 w-5 text-[#10b981]" />
                </div>
                <div>
                  <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">Setup Complete!</DialogTitle>
                  <DialogDescription className="text-xs text-[var(--text-secondary)]">
                    Backend setup completed successfully
                  </DialogDescription>
                </div>
              </div>
            </DialogHeader>

            <div className="space-y-3 mt-2">
              {/* Repositories imported */}
              <div className="space-y-2">
                <div className="flex items-center gap-2 p-3 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-color)]">
                  <Github className="h-4 w-4 text-[var(--text-secondary)]" />
                  <div className="flex-1">
                    <p className="text-xs font-medium text-[var(--text-primary)]">Source Repository</p>
                    <p className="text-[10px] text-[var(--text-secondary)]">{frontendRepoName || "Imported"}</p>
                  </div>
                  <Check className="h-3.5 w-3.5 text-[#10b981]" />
                </div>
                <div className="flex items-center gap-2 p-3 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-color)]">
                  <Github className="h-4 w-4 text-[var(--text-secondary)]" />
                  <div className="flex-1">
                    <p className="text-xs font-medium text-[var(--text-primary)]">Backend Repository</p>
                    <p className="text-[10px] text-[var(--text-secondary)]">{backendRepoName || "Created"}</p>
                  </div>
                  <Check className="h-3.5 w-3.5 text-[#10b981]" />
                </div>
              </div>

              {/* Cloud provider info (if selected) */}
              {selectedCloudProvider && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-color)]">
                  <Cloud className="h-4 w-4 text-[var(--text-secondary)]" />
                  <div className="flex-1">
                    <p className="text-xs font-medium text-[var(--text-primary)]">Cloud Provider</p>
                    <p className="text-[10px] text-[var(--text-secondary)]">{selectedCloudProvider.toUpperCase()}</p>
                  </div>
                  <Check className="h-3.5 w-3.5 text-[#10b981]" />
                </div>
              )}

              {/* Next steps info */}
              <div className="p-3 rounded-lg bg-primary/10 border border-primary/20">
                <p className="text-[10px] text-primary leading-relaxed">
                  <strong>Next:</strong> We&apos;ll review your repo, shape API endpoints and tests, and prepare a deployable backend with an integration pack{selectedCloudProvider ? ` on ${selectedCloudProvider.toUpperCase()}` : ""}.
                </p>
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <Button
                size="sm"
                onClick={handleClose}
                className="text-xs bg-primary hover:bg-primary-hover text-primary-foreground shadow-sm"
              >
                Go to Project
            </Button>
            </div>
          </>
        ) : (
          // Form state
          <>
            <DialogHeader>
              <div className="flex items-center gap-3 mb-2">
                <div className={cn(
                  "h-10 w-10 rounded-xl flex items-center justify-center",
                  "bg-primary/10 border border-primary/30"
                )}>
                  <Layers className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <DialogTitle className="text-sm font-semibold text-[var(--text-primary)]">Set Up Backend Repository</DialogTitle>
                  <DialogDescription className="text-xs text-[var(--text-secondary)]">
                    Choose where the backend code should live
                  </DialogDescription>
                </div>
              </div>
            </DialogHeader>

            <div className="space-y-4 mt-2">

              {/* Error message */}
              {error && (
                <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                  <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
          </div>
        )}

              {/* Info box explaining what this does */}
              <div className="p-3 rounded-lg bg-primary/10 border border-primary/20">
                <p className="text-[10px] text-primary dark:text-primary leading-relaxed mb-2">
                  <strong>What happens next:</strong>
                </p>
                <ul className="text-[10px] text-primary dark:text-primary leading-relaxed space-y-1 ml-4 list-disc">
                  <li>We&apos;ll review the imported project context</li>
                  <li>Generate backend code, API endpoints, and tests</li>
                  <li>Push the deployable backend and integration guidance to this repository</li>
                </ul>
              </div>

              {/* Repository Name */}
              <div className="grid gap-2">
                <Label className="text-xs text-[var(--text-secondary)]">Backend Repository Name</Label>
                <div className="relative">
                  <Input
                    value={backendRepoName}
                    onChange={(e) => setBackendRepoName(e.target.value)}
                    placeholder="my-app-backend"
                    disabled={isCreating}
                    className={cn(
                      "h-10 text-sm bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] focus:border-primary focus:ring-primary/20 disabled:opacity-50 pr-10",
                      repoNameError && "border-red-500 focus:border-red-500",
                      repoNameAvailable && !repoNameError && "border-[#10b981] focus:border-[#10b981]"
                    )}
                  />
                  {/* Validation indicator */}
                  <div className="absolute right-3 top-1/2 -translate-y-1/2">
                    {repoNameChecking && (
                      <Loader2 className="h-4 w-4 animate-spin text-[var(--text-secondary)]" />
                    )}
                    {!repoNameChecking && repoNameAvailable && !repoNameError && (
                      <Check className="h-4 w-4 text-[#10b981]" />
                    )}
                  </div>
                </div>
                {/* Error message */}
                {repoNameError && (
                  <p className="text-[10px] text-red-500">{repoNameError}</p>
                )}
                {/* Available message */}
                {!repoNameError && repoNameAvailable && !repoNameChecking && (
                  <p className="text-[10px] text-[#10b981]">Repository name is available</p>
                )}
                {/* Helper text */}
                {!repoNameError && !repoNameAvailable && !repoNameChecking && (
                  <p className="text-[10px] text-[var(--text-secondary)]">
                    This will create a new repository in your GitHub account
                  </p>
                )}
              </div>

              {/* Visibility */}
              <div className="grid gap-2">
                <Label className="text-xs text-[var(--text-secondary)]">Visibility</Label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => setRepoVisibility("public")}
                    disabled={isCreating}
                    className={cn(
                      "p-3 rounded-lg border-2 transition-all duration-200 text-left disabled:opacity-50",
                      repoVisibility === "public"
                        ? "border-primary bg-primary/5"
                        : "border-[var(--border-color)] hover:border-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]/50"
                    )}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <Globe className={cn(
                        "h-3.5 w-3.5",
                        repoVisibility === "public" ? "text-primary" : "text-[var(--text-secondary)]"
                      )} />
                      <p className="text-xs font-medium text-[var(--text-primary)]">Public</p>
                    </div>
                    <p className="text-[10px] text-[var(--text-secondary)]">Anyone can see</p>
                  </button>
                  <button
                    onClick={() => setRepoVisibility("private")}
                    disabled={isCreating}
                    className={cn(
                      "p-3 rounded-lg border-2 transition-all duration-200 text-left disabled:opacity-50",
                      repoVisibility === "private"
                        ? "border-primary bg-primary/5"
                        : "border-[var(--border-color)] hover:border-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]/50"
                    )}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <Lock className={cn(
                        "h-3.5 w-3.5",
                        repoVisibility === "private" ? "text-primary" : "text-[var(--text-secondary)]"
                      )} />
                      <p className="text-xs font-medium text-[var(--text-primary)]">Private</p>
                    </div>
                    <p className="text-[10px] text-[var(--text-secondary)]">Only you can see</p>
                  </button>
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <Button
                variant="outline"
                size="sm"
                onClick={handleClose}
                disabled={isCreating}
                className="text-xs border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] disabled:opacity-50"
              >
                Skip for now
              </Button>
              <Button
                size="sm"
                onClick={handleCreateBackendRepo}
                disabled={!backendRepoName || isCreating || repoNameChecking || !!repoNameError || (!isDemoMode && !repoNameAvailable)}
                className="text-xs bg-primary hover:bg-primary-hover text-primary-foreground shadow-sm disabled:opacity-50"
              >
                {isCreating ? (
                  <>
                    <Spinner className="h-3.5 w-3.5 mr-2" />
                    Creating...
                  </>
                ) : (
                  <>
                    <Github className="h-3.5 w-3.5 mr-2" />
                    Create Repository
                  </>
                )}
          </Button>
        </div>
          </>
        )}
        </DialogContent>
      </Dialog>
    </>
  );
}

// ============================================================================
// Project type for API response
// ============================================================================
interface Project {
  id: string;
  name: string;
  description: string | null;
  status: string;
  owner_id: string;
  team_id: string | null;
  repositories: Array<{
    id: string;
    type: string;
    name: string;
    full_name: string;
  }>;
  created_at: string;
  updated_at: string;
}

type DisplayProject = {
  id: string;
  name: string;
  status: string;
};

// ============================================================================
// Project Switcher Component - Uses global ProjectContext
// ============================================================================
import { useProject } from "@/lib/project-context";
import { useDemoOptional } from "@/lib/demo-context";

export function ProjectSwitcher() {
  const { isAuthenticated, user } = useAuth();
  // Use the global project context instead of local state
  const { projects, currentProject, isLoading: isLoadingProjects, setCurrentProject, refreshProjects } = useProject();
  // Use demo context to show active demo project
  const demo = useDemoOptional();
  const [isLoading, setIsLoading] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showGitHubImport, setShowGitHubImport] = useState(false);
  const [showLinkDialog, setShowLinkDialog] = useState(false);
  const [githubImportMode, setGitHubImportMode] = useState<SourceRepoType>("backend");
  const { theme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Demo project selection state for non-authenticated users
  // Initialize to 0 (must match server render to avoid hydration mismatch),
  // then restore from localStorage after mount.
  const [demoProjectIndex, setDemoProjectIndex] = useState(0);
  // Track if current demo is from API (imported) vs static mock
  const [isApiDemo, setIsApiDemo] = useState(false);
  const isGitHubLinked = user?.github_app_installed ?? false;

  // Restore persisted demo project index from localStorage after mount
  useEffect(() => {
    if (!isAuthenticated) {
      const saved = localStorage.getItem('demo-project-index');
      if (saved) {
        const idx = parseInt(saved, 10);
        if (!isNaN(idx) && idx !== 0) {
          setDemoProjectIndex(idx);
        }
      }
    }
  }, [isAuthenticated]);

  // Persist demo project index to localStorage when it changes
  useEffect(() => {
    if (!isAuthenticated && mounted) {
      localStorage.setItem('demo-project-index', demoProjectIndex.toString());
    }
  }, [demoProjectIndex, isAuthenticated, mounted]);
  
  // Display projects - real when authenticated, static mock when not signed in
  // IMPORTANT: When signed in with no projects, show empty state (not mock)
  const displayProjects = isAuthenticated 
    ? projects.map(p => ({ id: p.id, name: p.name, status: p.status }))
    : mockProjects; // Default to static mock projects

  // For signed-in users: show their project or null if none
  // For non-signed-in users: check if there's an active demo project from context
  const demoProject = demo?.project;
  const displayCurrentProject = isAuthenticated 
    ? currentProject 
    : demoProject 
      ? { id: `demo-${demoProject.slug}`, name: demoProject.name, status: demo.phase === "idle" ? "draft" : "analyzing" }
      : mockProjects[demoProjectIndex];

  const handleSwitchProject = async (project: DisplayProject) => {
    setIsLoading(true);
    await new Promise(resolve => setTimeout(resolve, 300));

    if (!isAuthenticated) {
      // For demo mode, find the index of the selected mock project
      const index = mockProjects.findIndex((p: any) => p.id === project.id);
      if (index >= 0) {
        setDemoProjectIndex(index);
        setIsApiDemo(false); // Switching to static mock
        // Dispatch custom event for page.tsx to pick up (static mock, not from API)
        const slug = mockProjects[index].slug;
        // Also persist slug in localStorage
        if (typeof window !== 'undefined') {
          localStorage.setItem('demo-project-slug', slug);
        }
        window.dispatchEvent(new CustomEvent('demoProjectChanged', {
          detail: { slug, isDemo: true, fromApi: false }
        }));
      }
    } else {
      // Find the full project if it's a real project
      const fullProject = projects.find(p => p.id === project.id);
      setCurrentProject(fullProject || null);
    }
    setIsLoading(false);
  };
  
  // Handler for importing a demo project from API (called from GitHub import dialog)
  const handleImportDemoProject = useCallback((demoProject: { slug: string; name: string }) => {
    setIsApiDemo(true);
    // Dispatch event to switch to API demo mode
    window.dispatchEvent(new CustomEvent('demoProjectChanged', { 
      detail: { slug: demoProject.slug, isDemo: true, fromApi: true } 
    }));
  }, []);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="flex items-center space-x-2 px-2 py-1.5 rounded-md hover:bg-[var(--bg-tertiary)] transition-colors">
            <div className={cn(
              "h-5 w-5 flex-shrink-0 rounded overflow-hidden flex items-center justify-center transition-colors",
              mounted && theme === "dark"
                ? "bg-primary/10"
                : "bg-gradient-to-br from-primary to-primary-strong"
            )}>
              <Cloud className={cn("h-3 w-3", mounted && theme === "dark" ? "text-primary" : "text-white")} />
            </div>
            <span className={cn(
              "text-xs font-medium truncate",
              isLoadingProjects ? "shimmer-text" : "text-[var(--text-primary)]"
            )}>
              {isLoadingProjects ? "Loading" : (displayCurrentProject?.name || (isAuthenticated ? "No Projects" : "Demo Project"))}
            </span>
            <ChevronDown className="h-3 w-3 text-[var(--text-secondary)]" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-64 bg-[var(--bg-primary)] border-[var(--border-color)]">
          {/* Current Project */}
          {displayCurrentProject ? (
          <div className="flex items-center space-x-2 p-2">
            <div className={cn(
              "h-7 w-7 rounded overflow-hidden flex items-center justify-center flex-shrink-0 transition-colors",
                mounted && theme === "dark"
                ? "bg-primary/10"
                : "bg-gradient-to-br from-primary to-primary-strong"
            )}>
                <Cloud className={cn("h-4 w-4", mounted && theme === "dark" ? "text-primary" : "text-white")} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-[var(--text-primary)] truncate">
                  {displayCurrentProject.name}
              </div>
              <div className="text-[10px] text-[var(--text-secondary)] capitalize">
                  {displayCurrentProject.status}
              </div>
            </div>
            <button
              onClick={() => setShowSettings(true)}
              className="flex items-center text-[10px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors border border-[var(--border-color)] rounded px-1.5 py-0.5 hover:bg-[var(--bg-tertiary)]"
            >
              <Settings className="mr-0.5 h-2.5 w-2.5" />
              Settings
            </button>
          </div>
          ) : isAuthenticated ? (
            /* Empty state for signed-in users with no projects */
            <div className="p-4 text-center">
              <div className="h-10 w-10 rounded-full bg-[var(--bg-tertiary)] flex items-center justify-center mx-auto mb-2">
                <FolderOpen className="h-5 w-5 text-[var(--text-secondary)]" />
              </div>
              <div className="text-xs font-medium text-[var(--text-primary)] mb-1">No projects yet</div>
              <div className="text-[10px] text-[var(--text-secondary)]">Import an existing backend from GitHub</div>
            </div>
          ) : null}

          {displayProjects.length > 1 && <DropdownMenuSeparator className="bg-[var(--border-color)]" />}

          {/* Other Projects */}
          {displayProjects
            .filter(p => p.id !== displayCurrentProject?.id)
            .map((project) => (
              <DropdownMenuItem
                key={project.id}
                onClick={() => handleSwitchProject(project)}
                className="flex items-center space-x-2 p-2 cursor-pointer group hover:bg-[var(--bg-tertiary)] focus:bg-[var(--bg-tertiary)]"
                disabled={isLoading}
              >
                <div className="h-7 w-7 rounded bg-[var(--bg-secondary)] flex items-center justify-center">
                  <FolderOpen className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-[var(--text-primary)] truncate">
                    {project.name}
                  </div>
                  <div className="text-[10px] text-[var(--text-secondary)] capitalize">
                    {project.status}
                  </div>
                </div>
                {isLoading ? (
                  <Spinner className="h-3 w-3 text-[var(--text-secondary)]" />
                ) : (
                  <ArrowRight className="h-3 w-3 text-[var(--text-secondary)] opacity-0 group-hover:opacity-100 transition-opacity" />
                )}
              </DropdownMenuItem>
            ))}

          <DropdownMenuSeparator className="bg-[var(--border-color)]" />

          {/* Import from GitHub */}
          <DropdownMenuItem
            onClick={() => {
              if (isAuthenticated && !isGitHubLinked) {
                setShowLinkDialog(true);
                return;
              }
              setGitHubImportMode("backend");
              setShowGitHubImport(true);
            }}
            className="flex items-center space-x-2 p-2 cursor-pointer hover:bg-[var(--bg-tertiary)] focus:bg-[var(--bg-tertiary)]"
          >
            <div className="h-7 w-7 rounded bg-[var(--bg-tertiary)] flex items-center justify-center">
              <Github className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-medium text-[var(--text-primary)]">Import Project</span>
                {!isAuthenticated && (
                  <span className={cn(
                    "text-[10px] px-2 py-0.5 rounded font-medium",
                    theme === "dark" && "bg-transparent text-amber-500 border border-amber-500/30",
                    theme === "light" && "bg-amber-500 text-white"
                  )}>
                    Demo Mode
                  </span>
                )}
              </div>
              <div className="text-[10px] text-[var(--text-secondary)]">Import from GitHub</div>
            </div>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {displayCurrentProject && (
        <ProjectSettingsDialog 
          open={showSettings} 
          onOpenChange={setShowSettings} 
          project={displayCurrentProject as any}
          onProjectDeleted={refreshProjects}
          onProjectUpdated={(updated) => {
            if (currentProject && currentProject.id === updated.id) {
              setCurrentProject({
                ...currentProject,
                name: updated.name,
                status: updated.status,
              });
            }
            void refreshProjects();
          }}
        />
      )}
      <GitHubImportDialog 
        open={showGitHubImport} 
        onOpenChange={setShowGitHubImport}
        defaultSourceRepoType={githubImportMode}
        onProjectCreated={refreshProjects}
        onGoToProject={(project) => {
          // Set the newly created project as current
          setCurrentProject(project);
        }}
      />
      <LinkGitHubDialog open={showLinkDialog} onOpenChange={setShowLinkDialog} />
    </>
  );
}

