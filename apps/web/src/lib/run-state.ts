import type { RunState } from "@/lib/api/types";

/**
 * How run states, verdicts and policy decisions are presented.
 *
 * The mapping lives here rather than at each call site so a state cannot be
 * coloured as success on one page and as failure on another. Semantic colours
 * are deliberately not derived from the brand hue: a verdict must keep its
 * meaning when the brand changes.
 */

export type Tone = "pass" | "fail" | "blocked" | "human" | "running" | "idle";

const STATE_TONES: Record<RunState, Tone> = {
  RECEIVED: "idle",
  SANITIZED: "running",
  NORMALIZED: "running",
  IMPACT_SCANNING: "running",
  UNAFFECTED: "idle",
  POLICY_EVALUATION: "running",
  HUMAN_REQUIRED: "human",
  WAITING_ON_OPERATOR: "human",
  BLOCKED: "blocked",
  PATCHING: "running",
  BUILDING: "running",
  RETRY_PATCH: "human",
  TESTING: "running",
  VERIFYING: "running",
  FAILED: "fail",
  PR_CREATING: "running",
  PR_CREATED: "pass",
};

/** States the state machine can still leave. Anything else has ended. */
const TERMINAL_STATES = new Set<RunState>([
  "UNAFFECTED",
  "HUMAN_REQUIRED",
  "BLOCKED",
  "FAILED",
  "PR_CREATED",
]);

export function runStateTone(state: RunState): Tone {
  return STATE_TONES[state] ?? "idle";
}

export function isTerminal(state: RunState): boolean {
  return TERMINAL_STATES.has(state);
}

/** True while a run is still moving, which is what should animate. */
export function isActive(state: RunState): boolean {
  return !TERMINAL_STATES.has(state);
}

export function humanizeState(state: string): string {
  return state
    .split("_")
    .map((word) => word.charAt(0) + word.slice(1).toLowerCase())
    .join(" ");
}

export function verdictTone(verdict: string): Tone {
  const normalized = verdict.toUpperCase();
  if (normalized === "PASS") return "pass";
  if (normalized === "FAIL") return "fail";
  // INCONCLUSIVE is not a pass. It gets the colour that means "a human has to
  // look", never the colour that means "this succeeded".
  return "human";
}

export function policyTone(decision: string): Tone {
  const normalized = decision.toUpperCase();
  if (normalized === "ALLOW") return "pass";
  if (normalized === "BLOCKED") return "blocked";
  return "human";
}

export function riskTone(risk: string): Tone {
  const normalized = risk.toLowerCase();
  if (normalized === "critical" || normalized === "high") return "fail";
  if (normalized === "medium") return "human";
  return "idle";
}

export function attemptTone(status: string): Tone {
  const normalized = status.toUpperCase();
  if (normalized === "SUCCEEDED") return "pass";
  if (normalized === "BUILD_FAILED" || normalized === "TESTS_FAILED") return "fail";
  if (normalized === "ABANDONED") return "idle";
  return "running";
}

export function outcomeTone(outcome: string): Tone {
  const normalized = outcome.toUpperCase();
  if (normalized === "SUCCEEDED") return "pass";
  if (normalized === "DENIED") return "blocked";
  return "fail";
}

const DETECTION_LABELS: Record<string, string> = {
  A_DETERMINISTIC: "Deterministic",
  B_SYNTAX_AWARE: "Syntax-aware",
  C_SEMANTIC: "Semantic",
};

export function detectionLabel(layer: string): string {
  return DETECTION_LABELS[layer] ?? layer;
}

/** Text and border classes per tone, used by the badge and dot components. */
export const TONE_CLASSES: Record<Tone, string> = {
  pass: "text-state-pass border-state-pass/35 bg-state-pass/10",
  fail: "text-state-fail border-state-fail/35 bg-state-fail/10",
  blocked: "text-state-blocked border-state-blocked/35 bg-state-blocked/10",
  human: "text-state-human border-state-human/35 bg-state-human/10",
  running: "text-state-running border-state-running/35 bg-state-running/10",
  idle: "text-state-idle border-state-idle/30 bg-state-idle/10",
};

export const TONE_DOT_CLASSES: Record<Tone, string> = {
  pass: "bg-state-pass",
  fail: "bg-state-fail",
  blocked: "bg-state-blocked",
  human: "bg-state-human",
  running: "bg-state-running",
  idle: "bg-state-idle",
};
