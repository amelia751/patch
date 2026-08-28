"use client";

import React, { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import { useTheme } from "@/lib/theme-context";
import { useProject } from "@/lib/project-context";
import { useArchitecture } from "@/lib/architecture-context";
import { useAuth } from "@/lib/auth-context";
import { useConsoleEvents } from "@/hooks/useConsoleEvents";
import { useConsolePanel } from "@/components/layout/app-layout";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Bell,
  CheckCircle2,
  Clock,
  Info,
  ChevronRight,
  Sparkles,
  GitBranch,
  Database,
  Code2,
  Zap,
  MessageSquare,
  RefreshCw,
  LaptopMinimalCheck,
} from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import {
  isMockNotificationId,
  // mockReleaseNotifications,
} from "@/components/interface/shared/mock-release-notifications";

type NotificationType = "success" | "pending" | "question" | "info" | "error";

interface NotificationAction {
  label: string;
  action_type: string;
  variant: "default" | "outline" | "ghost";
  data?: Record<string, unknown>;
}

interface Notification {
  id: string;
  project_id?: string;
  type: NotificationType;
  title: string;
  message: string;
  timestamp: string;
  priority: string;
  read: boolean;
  dismissed: boolean;
  details?: {
    label: string;
    items: string[];
  } | null;
  questions?: {
    question: string;
    options: string[];
  } | null;
  actions?: NotificationAction[];
  contract_ids?: string[];
  source_commit?: string;
  metadata?: Record<string, unknown>;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Hook to fetch notifications
function openChangesTab() {
  window.dispatchEvent(new CustomEvent("switchMainTab", { detail: { tab: "changes" } }));
}

function openConfigure(section: "connection" | "secrets", modal: "gcp" | "secret") {
  window.dispatchEvent(
    new CustomEvent("switchMainTab", {
      detail: { tab: "configure", configureSection: section, openCredentialModal: modal },
    }),
  );
}

function useNotifications(projectId: string | null, isAuthenticated: boolean, demoProject?: string, isDemoMode?: boolean, onDevOpsStarted?: (threadId: string) => void) {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [dismissedMockIds, setDismissedMockIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Temporary: fixtures stay off the bell while the inbox is forced empty.
  // const mockedReleases = useCallback((): Notification[] => {
  //   return mockReleaseNotifications()
  //     .filter((item) => !dismissedMockIds.includes(item.id))
  //     .map((item) => item as Notification);
  // }, [dismissedMockIds]);

  const applyList = useCallback(
    (_items: Notification[]) => {
      // Temporary: keep the bell, show an empty inbox. Restore the block
      // below to put live (and fixture) cards back in the dropdown.
      setNotifications([]);
      // if (isAuthenticated && !isDemoMode) {
      //   setNotifications(_items);
      //   return;
      // }
      // setNotifications(_items.length > 0 ? _items : mockedReleases());
    },
    [],
    // [isAuthenticated, isDemoMode, mockedReleases],
  );
  
  useEffect(() => {
    const clear = () => setNotifications([]);
    window.addEventListener("demoImportProject", clear);
    window.addEventListener("demoImportLiveProject", clear);
    return () => {
      window.removeEventListener("demoImportProject", clear);
      window.removeEventListener("demoImportLiveProject", clear);
    };
  }, []);
  
  const fetchNotifications = useCallback(async () => {
    if (isDemoMode || !isAuthenticated) {
      applyList([]);
      return;
    }

    if (!projectId) {
      setNotifications([]);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const url = `${API_URL}/api/notifications?project_id=${projectId}&limit=20`;
      const response = await fetch(url, {
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch notifications: ${response.status}`);
      }

      const data = await response.json();
      applyList(data.notifications || []);
    } catch (err) {
      console.error("Failed to fetch notifications:", err);
      setError(err instanceof Error ? err.message : "Failed to load notifications");
      applyList([]);
    } finally {
      setLoading(false);
    }
  }, [applyList, projectId, isAuthenticated, isDemoMode]);
  
  const consoleEvents = useConsoleEvents();

  // Live stream owns the bell for an authenticated project.
  useEffect(() => {
    if (isDemoMode || !isAuthenticated) return;
    if (consoleEvents.projectId !== projectId) return;
    if (consoleEvents.notifications == null) return;
    applyList(consoleEvents.notifications as Notification[]);
    setLoading(false);
    setError(null);
  }, [
    isDemoMode,
    isAuthenticated,
    projectId,
    consoleEvents.projectId,
    consoleEvents.notifications,
    applyList,
  ]);

  // Initial fetch for demo / signed-out. Authenticated users wait for the
  // console snapshot (and poll only if that stream drops). An empty live
  // list is a real answer — fixtures stay off the signed-in bell.
  useEffect(() => {
    if (isAuthenticated && !isDemoMode) return;
    fetchNotifications();
  }, [fetchNotifications, isAuthenticated, isDemoMode]);

  const navigateFromAction = (actionType: string) => {
    if (actionType === "view_changes" || actionType === "view_release" || actionType === "view_ops") {
      openChangesTab();
    } else if (actionType === "connect_gcp") {
      openConfigure("connection", "gcp");
    } else if (actionType === "add_secret") {
      openConfigure("secrets", "secret");
    }
  };

  const handleAction = async (notificationId: string, actionType: string, data?: Record<string, unknown>) => {
    if (isMockNotificationId(notificationId)) {
      navigateFromAction(actionType);
      if (actionType === "dismiss") {
        setDismissedMockIds((prev) =>
          prev.includes(notificationId) ? prev : [...prev, notificationId],
        );
        setNotifications((prev) => prev.filter((n) => n.id !== notificationId));
        return;
      }
      setNotifications((prev) =>
        prev.map((n) => (n.id === notificationId ? { ...n, read: true } : n)),
      );
      return;
    }

    navigateFromAction(actionType);

    // Demo mode handling (unauthenticated users OR clause projects)
    const isClauseProject = demoProject === "clause-frontend" || demoProject === "clause-legal-ai" || demoProject === "clause";
    if (!isAuthenticated || isClauseProject) {
      console.log("[Demo] Handling action:", actionType, "for notification:", notificationId);
      
      // Handle demo mode "Continue with DevOps" action
      if (actionType === "demo_continue_devops") {
        // Dispatch event for demo context to start DevOps
        window.dispatchEvent(new CustomEvent("demoStartDevOps"));
        // Mark as read
        setNotifications((prev) => 
          prev.map((n) => n.id === notificationId ? { ...n, read: true } : n)
        );
        return;
      }
      
      // Handle view ops tab action
      if (actionType === "view_ops") {
        // Dispatch event to switch to ops tab
        window.dispatchEvent(new CustomEvent("switchToOpsTab"));
        setNotifications((prev) => 
          prev.map((n) => n.id === notificationId ? { ...n, read: true } : n)
        );
        return;
      }
      
      if (actionType === "continue_devops") {
        // Emit event for console to open thread #2 with DevOps mock data
        window.dispatchEvent(new CustomEvent("openDevOpsThread", {
          detail: {
            threadId: "2",
            threadNumber: 2,
            demoProject: demoProject,
          }
        }));
        // Mark as read
        setNotifications((prev) => 
          prev.map((n) => n.id === notificationId ? { ...n, read: true } : n)
        );
        return;
      }
      
      if (actionType === "view_thread") {
        // Emit event for console to open thread #1 (analysis thread)
        window.dispatchEvent(new CustomEvent("openDevOpsThread", {
          detail: {
            threadId: "1",
            threadNumber: 1,
            demoProject: demoProject,
          }
        }));
        setNotifications((prev) => 
          prev.map((n) => n.id === notificationId ? { ...n, read: true } : n)
        );
        return;
      }
      
      if (actionType === "dismiss") {
        setNotifications((prev) => prev.filter((n) => n.id !== notificationId));
        return;
      }
      
      // Mark as read for other actions
      setNotifications((prev) => 
        prev.map((n) => n.id === notificationId ? { ...n, read: true } : n)
      );
      return;
    }
    
    // Authenticated mode - call API
    try {
      const response = await fetch(
        `${API_URL}/api/notifications/${notificationId}/action?project_id=${projectId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            action_type: actionType,
            contract_id: data?.contract_id,
            answer: data?.answer,
          }),
        }
      );
      
      if (!response.ok) {
        throw new Error(`Action failed: ${response.status}`);
      }
      
      const result = await response.json();
      
      // Handle specific actions
      if (actionType === "continue_devops" && result.start_url) {
        // Start the DevOps pipeline
        try {
          const startResponse = await fetch(
            `${API_URL}${result.start_url}`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              credentials: "include",
              body: JSON.stringify({ environment: "dev" }),
            }
          );
          
          if (startResponse.ok) {
            const startResult = await startResponse.json();
            console.log("DevOps pipeline started:", startResult);
            if (onDevOpsStarted && startResult.thread_id) {
              onDevOpsStarted(startResult.thread_id);
            }
          } else {
            console.error("Failed to start DevOps pipeline:", startResponse.status);
          }
        } catch (err) {
          console.error("Error starting DevOps:", err);
        }
        
        setNotifications((prev) => 
          prev.map((n) => n.id === notificationId ? { ...n, read: true } : n)
        );
        return;
      }
      
      if (actionType === "view_thread" && result.thread_id) {
        // Navigate to the thread (assuming console route)
        // For now, just close the dropdown - the user can click on console
        console.log("Navigate to thread:", result.thread_id, result.thread_number);
      }
      
      // Remove the notification from the list (for dismiss actions)
      if (actionType === "dismiss") {
        setNotifications((prev) => prev.filter((n) => n.id !== notificationId));
      } else {
        // Mark as read visually
        setNotifications((prev) => 
          prev.map((n) => n.id === notificationId ? { ...n, read: true } : n)
        );
      }
    } catch (err) {
      console.error("Failed to handle action:", err);
    }
  };
  
  const dismissNotification = async (notificationId: string) => {
    await handleAction(notificationId, "dismiss");
  };
  
  return {
    notifications,
    loading,
    error,
    refresh: fetchNotifications,
    handleAction,
    dismissNotification,
  };
}

interface NotificationItemProps {
  notification: Notification;
  onAction: (actionType: string, data?: Record<string, unknown>) => void;
  onDismiss: () => void;
}

function releaseTags(
  metadata?: Record<string, unknown>,
): { label: string; className: string }[] {
  const raw = metadata?.tags;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const row = item as { label?: unknown; className?: unknown };
    if (typeof row.label !== "string" || row.label.length === 0) return [];
    return [
      {
        label: row.label,
        className: typeof row.className === "string" ? row.className : "",
      },
    ];
  });
}

function NotificationItem({ notification, onAction, onDismiss }: NotificationItemProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null);
  const { theme } = useTheme();
  const { setActiveTab } = useArchitecture();
  const tags = releaseTags(notification.metadata);

  const handleActionClick = (action: NotificationAction) => {
    if (action.action_type === "dismiss") {
      onDismiss();
    } else if (action.action_type === "answer" && selectedAnswer) {
      onAction(action.action_type, { answer: selectedAnswer });
    } else {
      onAction(action.action_type, action.data);
    }
  };

  return (
    <div
      className={cn(
        "px-5 py-3 border-b border-[var(--border-color)] hover:bg-[var(--bg-tertiary)] transition-colors",
        "last:border-b-0",
        !notification.read && "bg-[var(--bg-secondary)]"
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-start gap-2 flex-1 min-w-0">
          <div className="flex-1 min-w-0">
            <div className="mb-1 space-y-1.5">
              <h4 className="text-xs font-semibold text-[var(--text-primary)] break-words [overflow-wrap:anywhere] leading-snug">
                {notification.title}
              </h4>
              {tags.length > 0 ? (
                <div className="flex items-center gap-2 flex-wrap">
                  {tags.map((tag) => (
                    <Badge
                      key={tag.label}
                      variant="outline"
                      className={cn("text-[9px]", tag.className)}
                    >
                      {tag.label}
                    </Badge>
                  ))}
                </div>
              ) : (
                <>
                  {notification.type === "pending" && (
                    <span className={cn(
                      "inline-flex shrink-0 whitespace-nowrap text-[10px] px-2 py-0.5 rounded-full font-medium",
                      theme === "dark" && "bg-transparent text-amber-500 border border-amber-500/30",
                      theme === "light" && "bg-amber-500 text-white"
                    )}>
                      Action Required
                    </span>
                  )}
                  {notification.type === "question" && (
                    <span className={cn(
                      "inline-flex shrink-0 whitespace-nowrap text-[10px] px-2 py-0.5 rounded-full font-medium",
                      theme === "dark" && "bg-transparent text-orange-500 border border-orange-500/30",
                      theme === "light" && "bg-orange-500 text-white"
                    )}>
                      Question
                    </span>
                  )}
                  {notification.type === "success" && (
                    <span className={cn(
                      "inline-flex shrink-0 whitespace-nowrap text-[10px] px-2 py-0.5 rounded-full font-medium",
                      theme === "dark" && "bg-transparent text-[#10b981] border border-[#10b981]/30",
                      theme === "light" && "bg-[#10b981] text-white"
                    )}>
                      Auto-Synced
                    </span>
                  )}
                </>
              )}
            </div>
            <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
              {notification.message}
            </p>
          </div>
        </div>
      </div>

      {/* Details (expandable) */}
      {notification.details && notification.details.label && (
        <div className="mt-2">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center gap-1 text-[10px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors mb-1"
          >
            <ChevronRight className={cn("h-3 w-3 transition-transform", isExpanded && "rotate-90")} />
            {notification.details.label}
          </button>
          {isExpanded && (
            <div className="mt-2 space-y-1 pl-4 border-l-2 border-[var(--border-color)]">
              {notification.details.items.map((item, index) => {
                // Check if item is a clickable link (format: "Label|action_type")
                const parts = item.split("|");
                const isLink = parts.length === 2;

                if (isLink) {
                  const [label, actionType] = parts;
                  const handleLinkClick = () => {
                    if (actionType === "view_architecture") {
                      setActiveTab("architecture");
                    } else if (actionType === "view_endpoints") {
                      setActiveTab("api");
                    } else if (actionType === "view_databases") {
                      setActiveTab("database");
                    } else if (actionType === "view_changes") {
                      onAction("view_changes");
                    }
                  };

                  return (
                    <button
                      key={index}
                      onClick={handleLinkClick}
                      className="block w-full text-[10px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] font-medium leading-relaxed transition-colors text-left"
                    >
                      {label} →
                    </button>
                  );
                }

                return (
                  <div key={index} className="text-[10px] text-[var(--text-secondary)] font-mono leading-relaxed">
                    {item}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Questions */}
      {notification.questions && notification.questions.question && isExpanded && (
        <div className="mt-3 p-2 bg-[var(--bg-secondary)] rounded-md border border-[var(--border-color)]">
          <p className="text-[10px] font-medium text-[var(--text-primary)] mb-2">
            {notification.questions.question}
          </p>
          <div className="space-y-1">
            {notification.questions.options.map((option, index) => (
              <button
                key={index}
                onClick={() => setSelectedAnswer(option)}
                className={cn(
                  "w-full text-left px-2 py-1.5 text-[10px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] rounded transition-colors border",
                  selectedAnswer === option 
                    ? "border-primary bg-primary/10 text-[var(--text-primary)]" 
                    : "border-transparent hover:border-[var(--border-color)]"
                )}
              >
                {option}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      {notification.actions && notification.actions.length > 0 && (
        <div className="mt-3 flex items-center gap-2">
          {notification.actions.map((action, index) => (
            <Button
              key={index}
              variant={action.variant as "default" | "outline" | "ghost"}
              size="sm"
              onClick={() => handleActionClick(action)}
              disabled={action.action_type === "answer" && !selectedAnswer && !!notification.questions?.question}
              className={cn(
                "h-6 text-[10px] px-2",
                action.variant === "default" && "bg-primary hover:bg-primary/90 text-primary-foreground",
                action.variant === "outline" && "border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]",
                action.variant === "ghost" && "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
              )}
            >
              {action.label}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}

export function NotificationCenter() {
  const [isOpen, setIsOpen] = useState(false);
  const [demoProject, setDemoProject] = useState<string | undefined>();
  const [isDemoMode, setIsDemoMode] = useState(false);
  const { currentProject } = useProject();
  const { isAuthenticated } = useAuth();
  const { focusThread } = useConsolePanel();

  // Listen for demo project changes and demo mode state
  useEffect(() => {
    // Check URL for demo project
    const params = new URLSearchParams(window.location.search);
    const urlDemoProject = params.get("demoProject");
    if (urlDemoProject) {
      setDemoProject(urlDemoProject);
    } else {
      // Default to ecommerce for unauthenticated demo users
      setDemoProject("ecommerce");
    }

    // Listen for custom event when demo project changes
    const handleDemoChange = (e: CustomEvent) => {
      setDemoProject(e.detail?.slug || "ecommerce");
    };
    window.addEventListener("demoProjectChanged", handleDemoChange as EventListener);
    
    // Listen for demo mode start (clears notifications) - BOTH replay and live modes
    const handleDemoImport = () => {
      console.log("[NotificationCenter] Demo import detected - setting isDemoMode=true");
      setIsDemoMode(true);
    };
    window.addEventListener("demoImportProject", handleDemoImport as EventListener);
    window.addEventListener("demoImportLiveProject", handleDemoImport as EventListener);
    
    // Listen for demo reset
    const handleDemoReset = () => {
      setIsDemoMode(false);
    };
    window.addEventListener("demoReset", handleDemoReset as EventListener);
    
    return () => {
      window.removeEventListener("demoProjectChanged", handleDemoChange as EventListener);
      window.removeEventListener("demoImportProject", handleDemoImport as EventListener);
      window.removeEventListener("demoImportLiveProject", handleDemoImport as EventListener);
      window.removeEventListener("demoReset", handleDemoReset as EventListener);
    };
  }, []);

  // Use demoProject for unauthenticated users, undefined for authenticated
  const effectiveDemoProject = !isAuthenticated ? demoProject : undefined;

  const {
    notifications,
    loading,
    error,
    refresh,
    handleAction,
    dismissNotification,
  } = useNotifications(currentProject?.id || null, isAuthenticated, effectiveDemoProject, isDemoMode, focusThread);

  // Count notifications needing action
  const actionCount = notifications.filter(
    (n) => n.type === "pending" || n.type === "question"
  ).length;

  const unreadCount = notifications.filter((n) => !n.read).length;

  return (
    <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              <button
                className={cn(
                  "relative p-1.5 rounded-md transition-colors border",
                  actionCount > 0
                    ? "text-amber-500 border-amber-500/30 hover:bg-amber-500/10"
                    : unreadCount > 0
                    ? "text-primary border-primary/30 hover:bg-primary/10"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] border-[var(--border-color)]"
                )}
              >
                <Bell className="h-4 w-4" />
                {(actionCount > 0 || unreadCount > 0) && (
                  <span className={cn(
                    "absolute -top-1 -right-1 h-4 w-4 text-white text-[9px] font-bold rounded-full flex items-center justify-center",
                    actionCount > 0 ? "bg-amber-500" : "bg-primary"
                  )}>
                    {actionCount || unreadCount}
                  </span>
                )}
              </button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent className="bg-[var(--bg-primary)] border-[var(--border-color)] text-[var(--text-primary)]">
            <p className="text-xs">
              {actionCount > 0 
                ? `${actionCount} notification${actionCount > 1 ? "s" : ""} need attention`
                : unreadCount > 0
                ? `${unreadCount} new notification${unreadCount > 1 ? "s" : ""}`
                : "No new notifications"}
            </p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <DropdownMenuContent
        align="end"
        className="w-80 max-h-[480px] overflow-hidden bg-[var(--bg-primary)] border-[var(--border-color)] p-0"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border-color)] bg-[var(--bg-secondary)]">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">Notifications</h3>
          </div>
          <button
            onClick={refresh}
            disabled={loading}
            className="p-1 text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            {loading ? (
              <Spinner className="h-4 w-4" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
          </button>
        </div>

        {/* Notifications List */}
        <div className="overflow-y-auto max-h-[500px]">
          {loading && notifications.length === 0 ? (
            <div className="flex items-center justify-center py-12">
              <Spinner className="h-6 w-6 text-[var(--text-tertiary)]" />
            </div>
          ) : error && notifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 px-4">
              <p className="text-sm text-red-500 mb-2">Failed to load</p>
              <button
                onClick={refresh}
                className="text-xs text-primary hover:underline"
              >
                Try again
              </button>
            </div>
          ) : notifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 px-4">
              <LaptopMinimalCheck className="h-8 w-8 text-[var(--text-tertiary)] mb-4" strokeWidth={1} />
              <p className="text-sm font-medium text-[var(--text-primary)] mb-1">All caught up!</p>
              <p className="text-xs text-[var(--text-secondary)] text-center max-w-[280px]">
                {currentProject
                  ? "We'll notify you when there are backend changes or when we need your input."
                  : "Select a project to see notifications."}
              </p>
            </div>
          ) : (
            <div>
              {notifications.map((notification) => (
                <NotificationItem
                  key={notification.id}
                  notification={notification}
                  onAction={(actionType, data) => {
                    void handleAction(notification.id, actionType, data);
                    if (
                      actionType === "view_changes" ||
                      actionType === "view_release" ||
                      actionType === "connect_gcp" ||
                      actionType === "add_secret"
                    ) {
                      setIsOpen(false);
                    }
                  }}
                  onDismiss={() => dismissNotification(notification.id)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        {notifications.length > 0 && (
          <div className="px-4 py-2 border-t border-[var(--border-color)] bg-[var(--bg-secondary)]">
            <button
              onClick={() => {
                openChangesTab();
                setIsOpen(false);
              }}
              className="w-full text-center text-[10px] text-primary hover:underline font-medium transition-all"
            >
              View releases →
            </button>
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
