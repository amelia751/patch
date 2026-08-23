/**
 * Header-bell fixtures. They are not live detections and do not claim a
 * sandbox, test, or PR outcome.
 *
 * The Releases inbox already has Need-you cards; this file copies that
 * product set so the dropdown is the same kind of notice while
 * `/api/notifications` is still empty.
 */

import {
  HARDCODED_PROJECT_CHANGES,
  isDocsOnly,
  type DetectionStatus,
  type ProjectChange,
} from "@/components/interface/ops/changes-tab/data";
import { HUMAN_REQUIRED_PAUSE } from "@/components/interface/ops/changes-tab/run-scripts";
import {
  CHANGE_KIND_LABELS,
  type ChangeKind,
} from "@/components/interface/provider/data";

/** Same chips as the Releases inbox — outline Badge, `rounded-md`. */
const STATUS_TAG: Record<DetectionStatus, { label: string; className: string }> = {
  needs_you: { label: "Needs you", className: "bg-amber-500 border-amber-500 text-white" },
  watching: {
    label: "Watching",
    className: "bg-[var(--bg-tertiary)] border-[var(--border-color)] text-[var(--text-secondary)]",
  },
  dismissed: {
    label: "Dismissed",
    className: "bg-[var(--bg-tertiary)] border-[var(--border-color)] text-[var(--text-secondary)]",
  },
};

const KIND_TONE: Record<ChangeKind, string> = {
  deprecation: "text-red-400 border-red-400/30",
  replacement: "text-amber-400 border-amber-400/30",
  new_identifier: "text-emerald-500 border-emerald-500/30",
  breaking_change: "text-red-400 border-red-400/30",
  feature: "text-emerald-500 border-emerald-500/30",
  fix: "text-sky-400 border-sky-400/30",
  issue: "text-amber-400 border-amber-400/30",
  security: "text-red-400 border-red-400/30",
  announcement: "text-[var(--text-secondary)] border-[var(--border-color)]",
  change: "text-[var(--text-secondary)] border-[var(--border-color)]",
  libraries: "text-sky-400 border-sky-400/30",
  other: "text-[var(--text-secondary)] border-[var(--border-color)]",
};

export const MOCK_NOTIFICATION_PREFIX = "mock-release-";

export function isMockNotificationId(id: string): boolean {
  return id.startsWith(MOCK_NOTIFICATION_PREFIX);
}

export interface MockReleaseNotification {
  id: string;
  type: "success" | "pending" | "question" | "info" | "error";
  title: string;
  message: string;
  timestamp: string;
  priority: string;
  read: boolean;
  dismissed: boolean;
  details?: { label: string; items: string[] } | null;
  questions?: { question: string; options: string[] } | null;
  actions?: Array<{
    label: string;
    action_type: string;
    variant: "default" | "outline" | "ghost";
    data?: Record<string, unknown>;
  }>;
  metadata?: Record<string, unknown>;
}

/**
 * Live inbox notes, minus layout-only rows.
 *
 * `ui-vertex-prefix-leftover` is a fixture but the subscribed project the
 * banner is written against does not surface it as Need you — leaving it
 * out keeps the digest at 2 / 5 / 1.
 */
function inboxNotes(): ProjectChange[] {
  return HARDCODED_PROJECT_CHANGES.filter(
    (change) => change.source === "fixture" && change.id !== "ui-vertex-prefix-leftover",
  );
}

function hoursAgo(hours: number): string {
  return new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();
}

function formatDay(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function usageLine(change: ProjectChange): string {
  if (isDocsOnly(change)) {
    return `${change.fileHits} docs refs · no runtime`;
  }
  if (change.fileHits > 0) {
    return `${change.fileHits} refs in ${change.fileCount} files`;
  }
  return "No usages in this project";
}

function releaseCard(change: ProjectChange, hours: number): MockReleaseNotification {
  const kind = CHANGE_KIND_LABELS[change.kind];
  const items = [
    `${kind} · ${change.provider} ${change.product}`,
    change.replacement ? `Replace with ${change.replacement}` : null,
    usageLine(change),
    change.repo ?? null,
    change.effectiveAt ? `Took effect ${formatDay(change.effectiveAt)}` : null,
    ...change.identifiers.slice(0, 3),
  ].filter((item): item is string => Boolean(item));

  return {
    id: `${MOCK_NOTIFICATION_PREFIX}${change.id}`,
    type: "pending",
    title: change.title,
    message: change.summary,
    timestamp: hoursAgo(hours),
    priority: "high",
    read: false,
    dismissed: false,
    details: {
      label: "Why this needs you",
      items,
    },
    actions: [
      {
        label: "Open in Changes",
        action_type: "view_changes",
        variant: "default",
        data: { change_id: change.id },
      },
      { label: "Dismiss", action_type: "dismiss", variant: "ghost" },
    ],
    metadata: {
      mock: true,
      change_id: change.id,
      product: change.product,
      tags: [
        STATUS_TAG[change.status],
        { label: CHANGE_KIND_LABELS[change.kind], className: KIND_TONE[change.kind] },
      ],
    },
  };
}

function runWaitingCard(): MockReleaseNotification {
  const [headline, ...rest] = HUMAN_REQUIRED_PAUSE.split(". ");
  return {
    id: `${MOCK_NOTIFICATION_PREFIX}human-required`,
    type: "pending",
    title: headline,
    message: rest.join(". "),
    timestamp: hoursAgo(2),
    priority: "high",
    read: false,
    dismissed: false,
    actions: [
      { label: "Connect GCP", action_type: "connect_gcp", variant: "default" },
      { label: "Add secret", action_type: "add_secret", variant: "outline" },
    ],
    metadata: { mock: true, tags: [STATUS_TAG.needs_you] },
  };
}

export function mockReleaseNotifications(): MockReleaseNotification[] {
  const needsYou = inboxNotes().filter((change) => change.status === "needs_you");
  return [
    runWaitingCard(),
    ...needsYou.map((change, index) => releaseCard(change, 4 + index * 18)),
  ];
}
