/**
 * A run's trace, turned into something worth looking at.
 *
 * This is a UI prototype. It reads a captured run and renders it; it never talks
 * to the control plane, and the fixtures it reads name a repository that does not
 * exist. Nothing here is on the live path.
 *
 * The problem it exists to solve: the console renders every `narration` row as a
 * paragraph of the sentence the backend happened to write, at one visual weight,
 * in source order. Six rows of setup become six sentences, two of which say
 * almost the same thing, and an operator hold reads as more prose. The trace
 * already carries what a run view needs — a phase per row, a timestamp per row,
 * and a tool name per action — and none of it was being used.
 *
 * So: group rows into the phases the state machine already names, keep the real
 * timestamps as durations, collapse runs of the same tool, and let the prose be
 * a short label instead of the whole sentence. The backend is not changed; the
 * same rows are simply read for the structure they have always had.
 */

export interface TraceRow {
  sequence: number;
  state: string;
  kind: string;
  verb: string;
  body: string;
  tool_type: string;
  tool_use_id: string;
  file_path: string;
  occurred_at: string;
}

export interface RunFixture {
  run_id: string;
  state: string;
  repository: string;
  change_id: string;
  base_sha: string;
  started_at: string;
  ended_at: string | null;
  pull_request_url: string | null;
  pull_request_number: number | null;
  trace: TraceRow[];
  artifacts: { kind: string; body: string | null; media_type: string }[];
  verification: Record<string, unknown> | null;
  pull_request: Record<string, unknown> | null;
}

export type StepTone = "neutral" | "good" | "warn" | "bad" | "think";

/** One line in the log. `at` is milliseconds from the start of the run. */
export interface Step {
  id: string;
  /** The short verb: what kind of thing this was. */
  label: string;
  /** The one piece of detail worth showing beside it, usually a path or command. */
  detail?: string;
  /** A short outcome, shown to the right of the detail. */
  outcome?: string;
  tone: StepTone;
  icon: IconName;
  at: number;
  durationMs: number;
  /** Terminal output, already fenced for `TerminalBlock`. */
  terminal?: string;
  /** A unified diff, already fenced for `DiffBlock`. */
  diff?: string;
  /** The full text, for steps whose whole point is what they said. */
  body?: string;
  /** Set when several identical tools were folded into this one row. */
  folded?: { label: string; detail: string }[];
}

export type IconName =
  | "dispatch"
  | "repo"
  | "sandbox"
  | "normalize"
  | "scan"
  | "policy"
  | "read"
  | "find"
  | "edit"
  | "shell"
  | "web"
  | "key"
  | "verify"
  | "pr"
  | "think"
  | "skill"
  | "eye";

export type PhaseId =
  | "setup"
  | "understand"
  | "decide"
  | "hold"
  | "patch"
  | "check"
  | "verify"
  | "publish";

export interface Phase {
  id: string;
  phase: PhaseId;
  title: string;
  /** A one-line summary shown when the phase is collapsed. */
  summary: string;
  at: number;
  durationMs: number;
  steps: Step[];
  /** Holds and the publish step stay open; long tool runs start collapsed. */
  collapsed: boolean;
  tone: StepTone;
}

export interface Timeline {
  phases: Phase[];
  totalMs: number;
  steps: number;
  repository: string;
  baseSha: string;
  changeId: string;
  prNumber: number | null;
  verdict: string | null;
}

const PHASE_TITLE: Record<PhaseId, string> = {
  setup: "Set up",
  understand: "Read the change",
  decide: "Decide",
  hold: "Waiting on you",
  patch: "Patch",
  check: "Check",
  verify: "Verify",
  publish: "Publish",
};

/** Which phase a trace row belongs to, from the run state it was written in. */
function phaseOf(row: TraceRow): PhaseId {
  const verb = row.verb || "";
  if (verb === "request_runtime_credentials") return "hold";
  // A resume is written with the run back in RECEIVED, which would file it under
  // Set up a second time. It is the end of the wait, so it belongs to the wait.
  if (row.kind === "narration" && /^(Operator supplied credentials|Continuing this run)/.test(row.body)) {
    return "hold";
  }
  if (/^(seed_static_manifest)$/.test(verb)) return "understand";
  if (/^(scan_repository|record_impact_report)$/.test(verb)) return "understand";
  if (/^(evaluate_policy|record_policy_decision)$/.test(verb)) return "decide";
  if (/^(open_pull_request)$/.test(verb)) return "publish";
  if (/verif/.test(verb)) return "verify";
  switch (row.state) {
    case "RECEIVED":
    case "SANITIZED":
      return "setup";
    case "NORMALIZED":
    case "IMPACT_SCANNING":
      return "understand";
    case "POLICY_EVALUATION":
      return "decide";
    case "WAITING_ON_OPERATOR":
    case "HUMAN_REQUIRED":
      return "hold";
    case "PATCHING":
    case "RETRY_PATCH":
      return "patch";
    case "BUILDING":
    case "TESTING":
      return "check";
    case "VERIFYING":
      return "verify";
    case "PR_CREATING":
    case "PR_CREATED":
      return "publish";
    default:
      return "patch";
  }
}

/** `name(args) → result`, split into its three parts. */
function parseCall(body: string): { name: string; args: string; result: string } {
  const arrow = body.indexOf(" → ");
  const head = arrow === -1 ? body : body.slice(0, arrow);
  const result = arrow === -1 ? "" : body.slice(arrow + 3).trim();
  const open = head.indexOf("(");
  if (open === -1 || !head.trimEnd().endsWith(")")) {
    return { name: head.trim(), args: "", result };
  }
  return {
    name: head.slice(0, open).trim(),
    args: head.slice(open + 1, head.trimEnd().length - 1),
    result,
  };
}

/**
 * One keyword argument out of a recorded call.
 *
 * Runs to the next `, key=` rather than to the next comma, because commands are
 * arguments too: `command=python3 -c "[print(r, d) for ...]"` has to survive.
 */
function arg(args: string, key: string): string {
  const match = new RegExp(`(?:^|,\\s*)${key}=(.*?)(?=,\\s*[a-z_]+=|$)`, "s").exec(args);
  return (match?.[1] ?? "").trim();
}

/** `[3 items]`, as the number. The recorder abbreviates lists this way. */
function count(value: string): number | null {
  const match = /^\[(\d+) items?\]$/.exec(value.trim());
  return match ? Number(match[1]) : null;
}

/** `[3 items]` as `3 identifiers`; anything else unchanged, minus its brackets. */
function listed(value: string, noun: string): string {
  const many = count(value);
  if (many !== null) return `${many} ${noun}${many === 1 ? "" : "s"}`;
  return value.replace(/^\[|\]$/g, "");
}

function humanSkill(id: string): string {
  return id.replace(/^google_/, "").replace(/gemini20/, "gemini 2.0").replace(/_/g, " ");
}

/**
 * A web-search request, as two words a person would actually read.
 *
 * The agent searches with boolean soup (`"responseModalities" "IMAGE" OR …`).
 * Quoted phrases and camelCase API names are the bits that distinguish one
 * query from the next; the operators and the repeated `generateContent` are not.
 */
function prettyQuery(raw: string): string {
  const quoted = [...raw.matchAll(/"([^"]+)"/g)].map((match) => match[1].trim()).filter(Boolean);
  const leftover = raw
    .replace(/"[^"]+"/g, " ")
    .split(/\s+/)
    .map((word) => word.trim())
    .filter((word) => word && !/^(OR|AND|NOT|google|gemini)$/i.test(word));
  const terms = [...quoted, ...leftover].filter((term, index, all) => {
    const lower = term.toLowerCase();
    if (lower === "generatecontent" || lower === "image" || lower === "text") return false;
    return all.findIndex((other) => other.toLowerCase() === lower) === index;
  });
  const pick = terms.slice(0, 3);
  return pick.join(" · ") || raw.replace(/"/g, "").trim().slice(0, 48);
}

function clip(text: string, max = 72): string {
  const one = text.split(/\n/)[0].trim().replace(/\.$/, "");
  if (one.length <= max) return one;
  return `${one.slice(0, max - 1).trimEnd()}…`;
}

/** The result of a tool call, cut to something that fits on one line. */
function shortOutcome(result: string): string {
  const first = result.split("\n")[0].trim();
  if (!first) return "";
  // `{a, b, c}` is a shape, not an outcome, and says nothing to a reader.
  if (first.startsWith("{") || first.startsWith("* ") || first.startsWith("**")) return "";
  return first.length > 64 ? `${first.slice(0, 61)}…` : first;
}

/**
 * The narration rows, as a label and a detail rather than a sentence.
 *
 * These six or so rows are the wall of prose this whole file exists to answer.
 * The sentence is kept on the step as `body` so nothing is lost, but what gets
 * drawn is the two or three words that differ between them.
 */
function fromNarration(row: TraceRow): Omit<Step, "id" | "at" | "durationMs"> | null {
  const body = row.body.trim();
  const one = body.split("\n")[0];

  let match = /^Dispatched to ([^.]+)\./.exec(one);
  if (match) {
    return { label: "Dispatched", detail: match[1], tone: "neutral", icon: "dispatch" };
  }
  match = /^Remediator claimed (\S+) at (\w+)/.exec(one);
  if (match) {
    return {
      label: "Claimed",
      detail: `${match[1].split("/").pop()} @ ${match[2].slice(0, 7)}`,
      tone: "neutral",
      icon: "repo",
    };
  }
  match = /^Fetched (\S+) at (\w+)/.exec(one);
  if (match) {
    return { label: "Fetched", detail: `pinned tree @ ${match[2].slice(0, 7)}`, tone: "neutral", icon: "repo" };
  }
  match = /^Allocating an isolated (\w+) sandbox/.exec(one);
  if (match) {
    return { label: "Sandbox", detail: `${match[1]} · isolated`, tone: "neutral", icon: "sandbox" };
  }
  match = /^Staged (\d+) files(?: from (\S+))?/.exec(one);
  if (match) {
    const kind = /isolated (\w+) sandbox/.exec(one)?.[1];
    const repo = match[2] ? ` from ${match[2].split("/").pop()}` : "";
    return {
      label: "Staged",
      detail: `${match[1]} files${repo}`,
      outcome: kind ? `${kind} sandbox` : "sandbox",
      tone: "neutral",
      icon: "sandbox",
    };
  }
  if (/^Operator supplied credentials/.test(one)) {
    return { label: "Credentials supplied", detail: "continuing this run", tone: "good", icon: "key" };
  }
  match = /GCP project (\S+) is connected/.exec(one);
  if (match) {
    return { label: "Resumed", detail: "GCP connected · same run", tone: "good", icon: "key" };
  }
  if (/no local repository check/.test(one)) return null;
  if (/^Baseline checks already fail/.test(one)) {
    return { label: "Baseline already failing", tone: "warn", icon: "shell" };
  }
  match = /^Local checks for this change: (.+)$/.exec(one);
  if (match) {
    return { label: "Local checks", detail: match[1].replace(/[`.]/g, ""), tone: "neutral", icon: "shell" };
  }
  if (/^Pull request opened/.test(one)) {
    return { label: "Pull request opened", tone: "good", icon: "pr" };
  }
  if (/^Starting the remediator/.test(one)) return null;
  return { label: one.replace(/\.$/, ""), tone: "neutral", icon: "eye" };
}

const READ_TOOLS = new Set([
  "read_file",
  "list_dir",
  "read_verification_evidence",
  "list_verification_evidence",
]);

/** A tool call, as a step. */
function fromAction(row: TraceRow): Omit<Step, "id" | "at" | "durationMs"> | null {
  const { name, args, result } = parseCall(row.body);
  const outcome = shortOutcome(result);

  switch (name) {
    case "seed_static_manifest":
      return { label: "Normalize", detail: "ChangeManifest", outcome: "identifiers as claims", tone: "neutral", icon: "normalize" };
    case "scan_repository":
      return { label: "Scan", detail: listed(arg(args, "identifiers"), "identifier"), outcome, tone: "neutral", icon: "scan" };
    case "record_impact_report":
      return {
        label: "Impact",
        detail: arg(args, "affected") === "True" ? "this repo is affected" : "not affected",
        outcome: arg(args, "migration_character") || undefined,
        tone: "neutral",
        icon: "scan",
      };
    case "evaluate_policy":
      return { label: "Policy", detail: listed(arg(args, "proposed_paths"), "path"), outcome, tone: outcome === "allow" ? "good" : "warn", icon: "policy" };
    case "record_policy_decision":
      // evaluate_policy already said allow or deny. Recording it is a second
      // row that only restates the same fact in louder words.
      return null;
    case "load_migration_skill":
      return { label: "Skill", detail: humanSkill(arg(args, "skill_id")), tone: "neutral", icon: "skill" };
    case "read_file":
    case "read_verification_evidence":
      return { label: "Read", detail: arg(args, "path") || arg(args, "name"), tone: "neutral", icon: "read" };
    case "list_dir":
      return { label: "List", detail: arg(args, "path"), tone: "neutral", icon: "find" };
    case "list_verification_evidence":
      return { label: "List evidence", tone: "neutral", icon: "find" };
    case "list_runtime_credentials":
      return { label: "Credentials", detail: "what's bound to this run", tone: "neutral", icon: "key" };
    case "search_web":
      return { label: "Search", detail: prettyQuery(arg(args, "request") || args), tone: "neutral", icon: "web" };
    case "request_runtime_credentials":
      return {
        label: "Needs you",
        detail: clip(arg(args, "reason") || (arg(args, "need") === "either" ? "GCP or a key" : arg(args, "need"))),
        body: arg(args, "reason"),
        tone: "warn",
        icon: "key",
      };
    case "record_patch_plan":
      return {
        label: "Plan",
        detail: `attempt ${arg(args, "attempt") || "1"}`,
        outcome: listed(arg(args, "assumptions"), "assumption"),
        tone: "neutral",
        icon: "edit",
      };
    case "record_verification_report":
      return { label: "Verdict", detail: arg(args, "verdict") || "recorded", tone: "good", icon: "verify" };
    case "computer_use_step":
      return { label: "Preview", detail: "proposed tree", tone: "neutral", icon: "eye" };
    case "open_pull_request":
      return { label: "Pull request", detail: arg(args, "head_branch"), tone: "good", icon: "pr" };
    case "run_command": {
      const command = arg(args, "command");
      const exit = /^exit (\d+)/.exec(result);
      const code = exit ? Number(exit[1]) : null;
      const tail = result.replace(/^exit \d+\s*/, "").trim();
      const refused = /is not on the .* allowlist/.test(result);
      if (refused) {
        return { label: "Refused", detail: command, outcome: "not on the allowlist", tone: "bad", icon: "shell" };
      }
      return {
        label: "Run",
        detail: command,
        outcome: code === null ? "" : `exit ${code}`,
        tone: code === 0 ? "good" : "bad",
        icon: "shell",
        terminal: tail ? ["```terminal", "# sandbox", `$ ${command}`, tail, "```"].join("\n") : undefined,
      };
    }
    case "apply_patch": {
      const applied = /applied/.test(result);
      return {
        label: "Edit",
        detail: row.file_path || "patch",
        outcome: applied ? "applied" : "rejected",
        tone: applied ? "good" : "bad",
        icon: "edit",
      };
    }
    default:
      if (READ_TOOLS.has(name)) return { label: "Read", detail: args, tone: "neutral", icon: "read" };
      return { label: name.replace(/_/g, " "), detail: outcome, tone: "neutral", icon: "eye" };
  }
}

const MS = (iso: string): number => new Date(iso).getTime();

/**
 * The calls a resume performs again.
 *
 * Resuming an operator hold re-runs the deterministic slices — normalize, scan,
 * policy — because they are cheap and their output is needed in hand before the
 * paused patch turn can carry on. So the trace holds two of each, and drawing
 * both invites the reading the console currently invites: that the run started
 * over. Model-driven calls are deliberately not on this list. An agent reading
 * the same file twice is something it chose to do, and consecutive repeats
 * already fold into one row.
 */
const REPLAYED_ON_RESUME = new Set([
  "seed_static_manifest",
  "scan_repository",
  "record_impact_report",
  "evaluate_policy",
  "record_policy_decision",
  "apply_patch",
]);

function plural(many: number, noun: string): string {
  return `${many} ${noun}${many === 1 ? "" : "s"}`;
}

/** What a folded row is counting, so it reads as English rather than as "6 files". */
const FOLDED_NOUN: Record<string, string> = {
  Search: "queries",
  Read: "files",
  List: "paths",
  Run: "commands",
  Edit: "edits",
  Thought: "thoughts",
};

/** Runs of three or more of the same label become one row that expands. */
function fold(steps: Step[]): Step[] {
  const out: Step[] = [];
  let index = 0;
  while (index < steps.length) {
    const step = steps[index];
    let end = index + 1;
    while (
      end < steps.length &&
      steps[end].label === step.label &&
      !steps[end].terminal &&
      !steps[end].diff &&
      !step.terminal &&
      !step.diff
    ) {
      end += 1;
    }
    const span = end - index;
    if (span >= 3) {
      const members = steps.slice(index, end);
      const last = members[members.length - 1];
      out.push({
        ...step,
        id: `${step.id}-folded`,
        detail: `${span} ${FOLDED_NOUN[step.label] ?? "steps"}`,
        outcome: "",
        durationMs: last.at + last.durationMs - step.at,
        folded: members.map((member) => ({ label: member.label, detail: member.detail ?? "" })),
        body: undefined,
      });
    } else {
      out.push(...steps.slice(index, end));
    }
    index = end;
  }
  return out;
}

function summarize(phase: PhaseId, steps: Step[], fixture: RunFixture): string {
  const find = (label: string) => steps.find((step) => step.label === label);
  /** How many of a label, counting the ones folded inside a folded row. */
  const tally = (label: string) =>
    steps.filter((step) => step.label === label).reduce((sum, step) => sum + (step.folded?.length ?? 1), 0);
  switch (phase) {
    case "setup": {
      const staged = find("Staged");
      return staged
        ? `${staged.detail} into ${staged.outcome ?? "a sandbox"}`
        : "sandbox ready";
    }
    case "understand": {
      const hits = find("Scan")?.outcome ?? "";
      return hits ? `${hits} at the pinned SHA` : "inventory joined at the pinned SHA";
    }
    case "decide": {
      const paths = find("Policy")?.detail;
      const verdict = find("Policy")?.outcome || "evaluated";
      return [verdict, paths].filter(Boolean).join(" · ");
    }
    case "hold":
      return find("Resumed")
        ? "paused for credentials, then the same run continued"
        : "waiting for GCP or a key";
    case "patch":
      return [
        tally("Read") && plural(tally("Read"), "read"),
        tally("Search") && plural(tally("Search"), "search").replace("searchs", "searches"),
        tally("Run") && plural(tally("Run"), "command"),
        tally("Refused") && `${tally("Refused")} refused`,
        tally("Edit") && plural(tally("Edit"), "edit"),
      ]
        .filter(Boolean)
        .join(" · ");
    case "check":
      return [
        tally("Run") && plural(tally("Run"), "local check"),
        tally("Preview") && "previewed the proposed tree",
      ]
        .filter(Boolean)
        .join(" · ") || "checked";
    case "verify": {
      const verdict = String((fixture.verification as { verdict?: string } | null)?.verdict ?? "");
      return [
        tally("Read") && `${plural(tally("Read"), "evidence file")} read`,
        verdict && `verdict ${verdict}`,
      ]
        .filter(Boolean)
        .join(" · ");
    }
    case "publish":
      return fixture.pull_request_number ? `#${fixture.pull_request_number} opened` : "pull request opened";
  }
}

/** A long tool run starts collapsed; short phases stay open so the page is not an outline. */
const COLLAPSE_AFTER = 8;

export function buildTimeline(fixture: RunFixture): Timeline {
  const origin = MS(fixture.started_at);
  const rows = [...fixture.trace].sort((a, b) => a.sequence - b.sequence);

  const diff = fixture.artifacts.find((artifact) => artifact.kind === "diff" && artifact.body)?.body ?? "";

  const built: { phase: PhaseId; step: Step }[] = [];
  const said = new Set<string>();

  rows.forEach((row, index) => {
    const at = MS(row.occurred_at) - origin;
    const next = rows[index + 1];
    const durationMs = Math.max(0, (next ? MS(next.occurred_at) : MS(row.occurred_at)) - MS(row.occurred_at));

    if (row.kind === "thought") {
      if (said.has(row.body)) return;
      said.add(row.body);
      built.push({
        phase: phaseOf(row),
        step: {
          id: `t${row.sequence}`,
          label: "Thought",
          detail: clip(row.body, 88),
          tone: "think",
          icon: "think",
          at,
          durationMs,
          body: row.body,
        },
      });
      return;
    }

    const drawn = row.kind === "narration" ? fromNarration(row) : fromAction(row);
    if (!drawn) return;

    const tool = row.kind === "action" ? parseCall(row.body).name : "";
    const repoName = fixture.repository.split("/").pop() ?? fixture.repository;
    const sha = fixture.base_sha.slice(0, 7);
    const framing: Record<string, string> = {
      seed_static_manifest: "Provider text is untrusted. Screen it before anything joins inventory.",
      scan_repository: `Join this change against ${repoName} @ ${sha}, not HEAD.`,
      read_file: "Read the binding at the pinned SHA before rewriting.",
      list_verification_evidence: "Grade the diff and the clean logs. Do not read the patch author’s plan.",
    };
    const frame = framing[tool];
    if (frame && !said.has(`thought|${frame}`)) {
      said.add(`thought|${frame}`);
      built.push({
        phase: phaseOf(row),
        step: {
          id: `t${row.sequence}`,
          label: "Thought",
          detail: clip(frame, 88),
          tone: "think",
          icon: "think",
          at,
          durationMs: 0,
          body: frame,
        },
      });
    }

    // Resuming replays the setup narration and the deterministic slices, so this
    // run's rows 14-24 repeat rows 3-11. It is the same run, so the second telling
    // is dropped rather than drawn under a second Set up and a second Decide.
    // Matched on what would be drawn, not on the recorded body, because the body
    // carries a per-sandbox scratch path that differs between the two attempts
    // while saying nothing a reader would notice.
    if (row.kind === "narration" || REPLAYED_ON_RESUME.has(parseCall(row.body).name)) {
      const fingerprint = `${drawn.label}|${drawn.detail ?? ""}|${drawn.outcome ?? ""}`;
      if (said.has(fingerprint)) return;
      said.add(fingerprint);
    }

    built.push({
      phase: phaseOf(row),
      step: {
        id: `s${row.sequence}`,
        at,
        durationMs,
        ...drawn,
        // The diff belongs where a reader can act on it: the branch that was
        // opened. `apply_patch` records only a digest, so an edit row cannot
        // honestly show the hunk it applied.
        diff: drawn.icon === "pr" && diff ? ["```diff", diff.trim(), "```"].join("\n") : undefined,
      },
    });
  });

  const phases: Phase[] = [];
  for (const { phase, step } of built) {
    const open = phases[phases.length - 1];
    if (open && open.phase === phase) {
      open.steps.push(step);
      continue;
    }
    phases.push({
      id: `${phase}-${step.id}`,
      phase,
      title: PHASE_TITLE[phase],
      summary: "",
      at: step.at,
      durationMs: 0,
      steps: [step],
      collapsed: false,
      tone: "neutral",
    });
  }

  const last = rows[rows.length - 1];
  const totalMs = last ? MS(last.occurred_at) - origin : 0;

  for (const phase of phases) {
    phase.steps = fold(phase.steps);
    const tail = phase.steps[phase.steps.length - 1];
    phase.durationMs = tail.at + tail.durationMs - phase.at;
    phase.summary = summarize(phase.phase, phase.steps, fixture);
    phase.collapsed = phase.steps.length > COLLAPSE_AFTER;
    // How the phase *ended*, not whether anything inside it went wrong. A patch
    // phase that hits a refused command and a failing baseline before landing a
    // clean edit has recovered, and marking it red says the opposite. Red is for
    // a phase whose last step failed; amber says something in here went wrong.
    const ended = phase.steps[phase.steps.length - 1];
    const stumbled = phase.steps.some((step) => step.tone === "bad");
    phase.tone =
      ended.tone === "bad"
        ? "bad"
        : phase.phase === "hold" || stumbled
          ? "warn"
          : phase.steps.some((step) => step.tone === "good")
            ? "good"
            : "neutral";
  }

  return {
    phases,
    totalMs,
    steps: built.length,
    repository: fixture.repository,
    baseSha: fixture.base_sha.slice(0, 7),
    changeId: fixture.change_id,
    prNumber: fixture.pull_request_number,
    verdict: String((fixture.verification as { verdict?: string } | null)?.verdict ?? "") || null,
  };
}

/** `1.2s`, `4m 3s`, `<1s` — never a bare millisecond count. */
export function humanMs(ms: number): string {
  if (ms < 1000) return "<1s";
  if (ms < 60000) return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)}s`;
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.round((ms % 60000) / 1000);
  return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
}
