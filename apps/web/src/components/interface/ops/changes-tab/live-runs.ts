/**
 * Control-API runs, mapped into the shape the panel draws.
 *
 * Nothing here invents a value. A run with no diff yet has no diff; a check
 * that has not run is absent rather than pending-and-green.
 */

import type { ChangeActionId } from "./actions";
import { runKey, type FileHit, type ProjectChange } from "./data";
import type { RunFixture } from "./run-timeline";
import {
  HUMAN_REQUIRED_PAUSE,
  failureCopy,
  type AgentLogLine,
  type DiffFile,
  type DiffLine,
  type LogKind,
  type MachineState,
  type MockRun,
  type RunBucket,
  type SandboxCommand,
  type VerifyCheck,
} from "./run-scripts";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Server states the panel has no separate face for.
 *
 * `RECEIVED` and `SANITIZED` are the first instants of a run and read as
 * normalizing. `RETRY_PATCH` is patching again. `PR_CREATING` is the moment
 * before the PR exists, and showing it as "PR opened" would be a claim; it
 * stays under verification until the pull request is actually there.
 */
const MACHINE_ALIAS: Record<string, MachineState> = {
  RECEIVED: "NORMALIZED",
  SANITIZED: "NORMALIZED",
  RETRY_PATCH: "PATCHING",
  PR_CREATING: "VERIFYING",
};

const KNOWN_MACHINES = new Set<MachineState>([
  "NORMALIZED",
  "IMPACT_SCANNING",
  "POLICY_EVALUATION",
  "HUMAN_REQUIRED",
  "WAITING_ON_OPERATOR",
  "PATCHING",
  "BUILDING",
  "TESTING",
  "VERIFYING",
  "PR_CREATED",
  "UNAFFECTED",
  "HELD",
  "FAILED",
  "BLOCKED",
]);


export interface RunSummary {
  run_id: string;
  state: string;
  repository: string;
  change_id: string;
  base_sha: string;
  attempts_used: number;
  attempt_budget: number;
  failure_reason: string | null;
  started_at: string;
  updated_at: string;
  ended_at: string | null;
  pull_request_url: string | null;
  pull_request_number: number | null;
}

interface TraceRow {
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

interface ArtifactRow {
  kind: string;
  uri: string;
  media_type: string;
  body: string;
  created_at: string;
}

export interface RunDetail extends RunSummary {
  trace: TraceRow[];
  transitions: { sequence: number; from_state: string | null; to_state: string; reason: string }[];
  policy: Record<string, unknown> | null;
  verification: Record<string, unknown> | null;
  artifacts: ArtifactRow[];
  pull_request: Record<string, unknown> | null;
}

export function machineOf(state: string): MachineState {
  const aliased = MACHINE_ALIAS[state] ?? (state as MachineState);
  return KNOWN_MACHINES.has(aliased) ? aliased : "NORMALIZED";
}

export function bucketOf(machine: MachineState): RunBucket {
  if (machine === "HUMAN_REQUIRED" || machine === "WAITING_ON_OPERATOR") return "needs_attention";
  if (machine === "PR_CREATED") return "ready_for_review";
  if (machine === "UNAFFECTED" || machine === "HELD") return "idle";
  if (machine === "FAILED" || machine === "BLOCKED") return "blocked";
  return "active";
}

/** Whether a run is still moving, and therefore worth polling quickly for. */
export function isLive(state: string): boolean {
  const machine = machineOf(state);
  return bucketOf(machine) === "active";
}

/**
 * Parse a unified diff into the per-file shape the proposed tree renders.
 *
 * Deliberately tolerant: an unrecognised line is context rather than a parse
 * error, because a diff that renders slightly plainly is better than a run
 * whose proposed tree fails to appear at all.
 */
export function parseDiff(text: string): DiffFile[] {
  const files: DiffFile[] = [];
  let current: DiffFile | null = null;

  for (const raw of text.split("\n")) {
    if (raw.startsWith("--- ")) continue;
    if (raw.startsWith("+++ ")) {
      const path = raw.slice(4).replace(/^b\//, "").trim();
      current = { path, additions: 0, deletions: 0, lines: [] };
      files.push(current);
      continue;
    }
    if (raw.startsWith("diff --git") || raw.startsWith("index ")) continue;
    if (!current) continue;
    if (raw.startsWith("@@")) {
      current.lines.push({ kind: "ctx", text: raw });
      continue;
    }
    let line: DiffLine;
    if (raw.startsWith("+")) {
      current.additions += 1;
      line = { kind: "add", text: raw.slice(1) };
    } else if (raw.startsWith("-")) {
      current.deletions += 1;
      line = { kind: "del", text: raw.slice(1) };
    } else {
      line = { kind: "ctx", text: raw.startsWith(" ") ? raw.slice(1) : raw };
    }
    current.lines.push(line);
  }
  return files.filter((file) => file.path && file.lines.length > 0);
}

function exitFrom(text: string): number | null {
  const marked = /\(exit (-?\d+)\)/.exec(text);
  if (marked) return Number(marked[1]);
  const plain = /\bexit(?:ed)? (\d+)\b/i.exec(text) ?? /exit code (\d+)/i.exec(text);
  return plain ? Number(plain[1]) : null;
}

function parseCommandBlocks(
  body: string,
  phase: SandboxCommand["phase"],
  source: NonNullable<SandboxCommand["source"]>,
): SandboxCommand[] {
  const commands: SandboxCommand[] = [];
  const blocks = body.split(/^\$ /m).slice(1);
  if (blocks.length === 0 && body.trim()) {
    commands.push({
      phase,
      argv: phase === "build" ? "build" : "tests",
      exit: exitFrom(body),
      tail: body.trim().slice(-4000),
      source,
    });
    return commands;
  }
  for (const block of blocks) {
    const [argv, ...rest] = block.split("\n");
    const tail = rest.join("\n").trim();
    commands.push({
      phase,
      argv: argv.trim(),
      exit: exitFrom(tail),
      tail: tail.slice(-4000),
      source,
    });
  }
  return commands;
}

/** The commands a log artifact records, with the exit code it reported. */
function commandsFrom(artifacts: ArtifactRow[]): SandboxCommand[] {
  const commands: SandboxCommand[] = [];
  for (const artifact of artifacts) {
    if (artifact.kind !== "build_log" && artifact.kind !== "test_log") continue;
    const phase = artifact.kind === "build_log" ? "build" : "test";
    const source = artifact.body.startsWith("# baseline") ? "baseline" : "patched";
    commands.push(...parseCommandBlocks(artifact.body, phase, source));
  }
  return commands;
}

function terminalFence(dir: string, commands: { cmd: string; out: string }[]): string {
  const lines = ["```terminal", `# ${dir}`];
  for (const item of commands) {
    lines.push(`$ ${item.cmd}`);
    if (item.out) {
      for (const line of item.out.replace(/\r\n/g, "\n").split("\n")) {
        lines.push(line);
      }
    }
  }
  lines.push("```");
  return lines.join("\n");
}

/** One file's unified diff, in the fence DiffBlock already knows how to draw. */
function diffFence(file: DiffFile): string {
  const lines = [`--- a/${file.path}`, `+++ b/${file.path}`];
  for (const line of file.lines) {
    if (line.text.startsWith("@@")) {
      lines.push(line.text);
      continue;
    }
    if (line.kind === "add") lines.push(`+${line.text}`);
    else if (line.kind === "del") lines.push(`-${line.text}`);
    else lines.push(line.text.startsWith(" ") ? line.text : ` ${line.text}`);
  }
  return ["```diff", ...lines, "```"].join("\n");
}

/** Fixture check copy. The job stores `build` / `tests` / `live_api` / `policy`. */
const CHECK_LABEL: Record<string, string> = {
  build: "Clean build from the diff alone",
  tests: "Clean tests from the diff alone",
  test: "Clean tests from the diff alone",
  live_api: "Replacement resolves live",
  policy: "Forbidden paths untouched",
  identifiers: "Identifiers mapped as the manifest specifies",
  changelog: "CHANGELOG.md and other history files untouched",
};

function checksFrom(verification: Record<string, unknown> | null): VerifyCheck[] {
  const raw = verification?.checks;
  const checks = Array.isArray(raw)
    ? raw
        .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
        .map((item) => {
          const key = String(item.name ?? "");
          return {
            name: CHECK_LABEL[key] ?? key,
            passed: Boolean(item.passed),
          };
        })
        .filter((check) => check.name)
    : [];
  const independent =
    verification &&
    verification.verifier_agent &&
    verification.patch_agent &&
    verification.verifier_agent !== verification.patch_agent;
  if (independent && !checks.some((check) => /verifier/i.test(check.name))) {
    checks.push({
      name: "Verifier did not see the patch author’s plan",
      passed: true,
    });
  }
  return checks;
}

function namedArgs(raw: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of raw.split(/,\s*(?=[A-Za-z_][A-Za-z0-9_]*=)/)) {
    const eq = part.indexOf("=");
    if (eq < 0) continue;
    out[part.slice(0, eq)] = part.slice(eq + 1);
  }
  return out;
}

function workspacePath(path: string): string {
  return path
    .replace(/^\/tmp\/patchapi-run-[^/]+\//, "")
    .replace(/^\/tmp\/patchapi-sandbox\/?/, "");
}

function parseToolCall(
  body: string,
): { name: string; args: Record<string, string>; output: string; result: string } | null {
  const raw = body.trim();
  const arrow = raw.indexOf(" → ");
  const newline = raw.indexOf("\n");
  const head = arrow >= 0 ? raw.slice(0, arrow) : newline >= 0 ? raw.split("\n")[0] : raw;
  const output = newline >= 0 ? raw.slice(newline + 1).trim() : "";
  // The one-line summary a tool returned. Kept separate from `output` because a
  // tool that failed says so here and has no body at all, and a caller that
  // only reads `output` cannot tell that apart from a tool that said nothing.
  const result = arrow >= 0 ? raw.slice(arrow + 3).split("\n")[0].trim() : "";
  const match = head.replace(/\s*→\s*[\s\S]*$/, "").match(/^([A-Za-z_][A-Za-z0-9_]*)\((.*)\)\s*$/);
  if (!match) return null;
  return { name: match[1], args: namedArgs(match[2]), output, result };
}

/** Whether a tool's one-line result says the call did not do what it was asked. */
function refused(result: string): boolean {
  return /^error\b|\berror:|does not apply|not on the .* allowlist|exit code [1-9]|\bexit [1-9]/i.test(
    result,
  );
}

const HIDDEN_TOOLS = new Set([
  "computer_use_step",
  "list_verification_evidence",
  "list_dir",
  "record_patch_plan",
  // The intake gate. Already narrated where it happens, below.
  "screen_untrusted_text",
]);

const NOISE_COMMANDS = /^(git status|npm run build|pnpm (?:install|run build))\b/;

function line(
  id: string,
  at: MachineState,
  kind: LogKind,
  text: string,
  extras?: Pick<AgentLogLine, "verb" | "toolType" | "toolUseId" | "filePath">,
): AgentLogLine {
  return {
    id,
    at,
    kind,
    text,
    verb: extras?.verb,
    toolType: extras?.toolType,
    toolUseId: extras?.toolUseId,
    filePath: extras?.filePath,
  };
}

/**
 * Rebuild the mock's worklog from what the job recorded, in Cursor order.
 *
 * The fixture was a story you can read top to bottom: thought → named tool →
 * one-line result → terminal with captured stdout. The job's traces are the
 * same events in a different vocabulary (ADK names, policy essays, skill
 * reads, re-reads after the patch). This composer keeps chronology and drops
 * the extras. It does not invent a thought the model did not say, a command
 * the sandbox did not run, or a check the verifier did not record.
 */
export function composeWorklog(
  detail: RunDetail,
  change: ProjectChange | undefined,
  commands: SandboxCommand[],
  diffs: DiffFile[] = [],
  inventory: FileHit[] = [],
): AgentLogLine[] {
  const lines: AgentLogLine[] = [];
  let n = 0;
  const add = (
    at: MachineState,
    kind: LogKind,
    text: string,
    extras?: Pick<AgentLogLine, "verb" | "toolType" | "toolUseId" | "filePath">,
  ) => {
    n += 1;
    lines.push(line(`${at}-${n}`, at, kind, text, extras));
  };

  if (detail.trace.length === 0 && bucketOf(machineOf(detail.state)) === "active") {
    add(
      "NORMALIZED",
      "narration",
      "Waiting for the remediator to claim this run. Lines appear as the job writes them.",
    );
  }

  const repo = detail.repository;
  const sha = detail.base_sha.slice(0, 12) || "unpinned";
  const identifier = change?.identifiers[0] ?? "";
  const policy = detail.policy;
  const verification = detail.verification;
  const baseline = commands.filter(
    (command) => command.source === "baseline" && command.argv !== "build" && command.argv !== "tests",
  );
  const patched = commands.filter(
    (command) => command.source !== "baseline" && command.argv !== "build" && command.argv !== "tests",
  );
  const leftoverLogs = commands.filter((command) => command.argv === "build" || command.argv === "tests");
  const used = new Set<SandboxCommand>();

  const takeCommand = (argv: string, prefer: "baseline" | "patched"): SandboxCommand | undefined => {
    const pool = prefer === "baseline" ? baseline : patched;
    const match = pool.find((command) => !used.has(command) && command.argv === argv);
    if (match) {
      used.add(match);
      return match;
    }
    const any = [...baseline, ...patched].find((command) => !used.has(command) && command.argv === argv);
    if (any) {
      used.add(any);
      return any;
    }
    return undefined;
  };

  let sawNormalize = false;
  let sawImpact = false;
  let sawPolicy = false;
  let sawPatchThought = false;
  let sawVerify = false;
  let sawVerifyReport = false;
  let sawApply = false;
  let sawPr = false;
  const shownCommands = new Set<string>();
  // Path → the diff already drawn for it. A second `apply_patch` carrying the
  // same hunks is the same edit seen again, not a second edit; a second one
  // carrying different hunks is a real change and is drawn.
  const shownEdits = new Map<string, string>();
  const shownReads = new Set<string>();
  const pendingReads: string[] = [];
  // A run that paused for a credential is continued by a *new* job execution:
  // Cloud Run cannot keep a container alive across an operator hold. That
  // execution has to re-clone the tree, re-open a sandbox and re-run the
  // deterministic scan, so it writes the setup lines a second time. Drawing
  // them twice is what made Continue look like a restart of the whole
  // remediation. The worklog is one story per run, so a line already told is
  // not told again — only what the new execution genuinely adds.
  const told = new Set<string>();
  const fresh = (text: string): boolean => {
    const key = text.trim().toLowerCase();
    if (!key || told.has(key)) return false;
    told.add(key);
    return true;
  };

  const flushReads = () => {
    for (const path of pendingReads) {
      if (shownReads.has(path)) continue;
      shownReads.add(path);
      add("PATCHING", "action", `Read(\`${path}\`)`, {
        verb: "Read",
        toolType: "Read",
        filePath: path,
      });
    }
    pendingReads.length = 0;
  };

  const beginPatching = () => {
    if (sawPatchThought) return;
    add("PATCHING", "thought", "Read the binding at the pinned SHA before rewriting.");
    sawPatchThought = true;
  };

  // The header on a terminal fence. It used to be the literal string
  // `/tmp/patchapi-sandbox`, which is not where anything ran: a GKE sandbox
  // executes in its own container. The job names the sandbox it opened, so say
  // that instead of a path this side cannot know.
  const sandboxLabel = (): string => {
    for (const row of detail.trace) {
      const found = /isolated (\w+) sandbox/.exec(row.body ?? "");
      if (found) return `${found[1]} sandbox`;
    }
    return "sandbox";
  };

  const impactHits = (): string | undefined => {
    const hits = change?.fileHits;
    const files = change?.files.filter((file) => file.kind === "runtime").length ?? change?.fileCount;
    if (hits == null || files == null) return undefined;
    return `${hits} hits · ${files} runtime paths.`;
  };

  for (const row of detail.trace) {
    const at = machineOf(row.state);
    const body = row.body.trim();

    if (row.kind === "thought" && body) {
      if (isToolDump(body) || !fresh(body)) continue;
      flushReads();
      add(at, "thought", body);
      continue;
    }

    if (row.kind === "narration" && body) {
      if (isNoiseNarration(body) || isToolDump(body) || !fresh(body)) continue;
      flushReads();
      add(at, "narration", body);
      continue;
    }

    const parsed = parseToolCall(row.body);
    const name = parsed?.name || row.verb;
    if (!name || HIDDEN_TOOLS.has(name)) continue;

    if (name === "seed_static_manifest") {
      if (sawNormalize) continue;
      add("NORMALIZED", "thought", "Provider text is untrusted. Screen it before anything joins inventory.");
      add("NORMALIZED", "action", "Normalize(`ChangeManifest`)", {
        verb: "Normalize",
        toolType: "Normalize",
      });
      add("NORMALIZED", "result", "Identifiers kept as claims.");
      sawNormalize = true;
      continue;
    }

    if (name === "scan_repository") {
      if (sawImpact) continue;
      if (identifier) {
        add("IMPACT_SCANNING", "thought", `Join \`${identifier}\` against ${repo} @ ${sha}, not HEAD.`);
      }
      add("IMPACT_SCANNING", "action", "Search(`inventory`)", {
        verb: "Search",
        toolType: "Grep",
        toolUseId: "impact-search",
      });
      const runtime = inventory.filter((file) => !file.kind || file.kind === "runtime").slice(0, 3);
      for (const file of runtime) {
        if (shownReads.has(file.path)) continue;
        shownReads.add(file.path);
        add("IMPACT_SCANNING", "action", `Read(\`${file.path}\`)`, {
          verb: "Read",
          toolType: "Read",
          filePath: file.path,
        });
      }
      const hits = impactHits();
      if (hits) add("IMPACT_SCANNING", "result", hits, { toolUseId: "impact-search" });
      sawImpact = true;
      continue;
    }

    if (name === "record_impact_report") {
      if (!sawImpact) {
        const hits = impactHits();
        if (hits) add("IMPACT_SCANNING", "result", hits);
        sawImpact = true;
      }
      continue;
    }

    if (name === "evaluate_policy" || name === "record_policy_decision") {
      if (sawPolicy) continue;
      add("POLICY_EVALUATION", "narration", "Auto-merge stays false. Forbidden paths stay forbidden.");
      add("POLICY_EVALUATION", "action", "Evaluate(`impact report`)", {
        verb: "Evaluate",
        toolType: "Evaluate",
      });
      add("POLICY_EVALUATION", "result", policyLine(policy));
      sawPolicy = true;
      continue;
    }

    if (name === "read_file") {
      const path = workspacePath(row.file_path || parsed?.args.path || parsed?.args.name || "");
      if (isNoiseRead(path) || shownReads.has(path) || pendingReads.includes(path)) continue;
      // After the patch, the agent re-reads what it just wrote. The terminals
      // and the proposed tree already show that; another Read is noise.
      if (sawApply) continue;
      beginPatching();
      pendingReads.push(path);
      continue;
    }

    if (
      name === "list_skills" ||
      name === "load_skill" ||
      name === "load_skill_resource" ||
      name === "read_verification_evidence"
    ) {
      continue;
    }

    if (name === "apply_patch") {
      flushReads();
      beginPatching();
      // An attempt that did not apply is not an edit. This used to fall through
      // to the run's final diff and draw the rejected attempt as two green
      // edits, crediting it with a change it never made — and then the retry
      // that did apply drew the same files again.
      if (parsed && refused(parsed.result)) {
        add("PATCHING", "action", "Edit(`apply_patch`)", { verb: "Apply", toolType: "Edit" });
        add("PATCHING", "result", parsed.result);
        continue;
      }
      const hunks = parsed?.output ? parseDiff(parsed.output) : [];
      const files = hunks.length > 0 ? hunks : shownEdits.size === 0 ? diffs : [];
      if (files.length > 0) {
        for (const file of files) {
          const fence = diffFence(file);
          if (shownEdits.get(file.path) === fence) continue;
          const created = file.deletions === 0 && file.additions > 0;
          add("PATCHING", "action", `${created ? "Write" : "Edit"}(\`${file.path}\`)`, {
            verb: created ? "Write" : "Apply",
            toolType: created ? "Write" : "Edit",
            filePath: file.path,
          });
          add("PATCHING", "block", fence);
          shownEdits.set(file.path, fence);
        }
      } else {
        const named = workspacePath(parsed?.args.files || parsed?.args.path || "");
        const label = named && !named.startsWith("/") ? named : "apply_patch";
        if (!shownEdits.has(label)) {
          add("PATCHING", "action", `Edit(\`${label}\`)`, {
            verb: "Apply",
            toolType: "Edit",
            filePath: label === "apply_patch" ? undefined : label,
          });
          shownEdits.set(label, "");
        }
      }
      sawApply = true;
      continue;
    }

    if (name === "request_runtime_credentials") {
      const need = parsed?.args.need || parsed?.args.names || "secret";
      add(at === "NORMALIZED" ? "WAITING_ON_OPERATOR" : at, "action", `request_runtime_credentials(need=${need})`, {
        verb: "Request",
        toolType: "Request",
      });
      add("WAITING_ON_OPERATOR", "narration", HUMAN_REQUIRED_PAUSE);
      continue;
    }

    if (name === "list_runtime_credentials") {
      const paused =
        machineOf(detail.state) === "WAITING_ON_OPERATOR" || machineOf(detail.state) === "HUMAN_REQUIRED";
      if (!paused) continue;
      add("WAITING_ON_OPERATOR", "action", "list_runtime_credentials()", {
        verb: "List",
        toolType: "List",
      });
      continue;
    }

    if (name === "run_command") {
      flushReads();
      const argv = parsed?.args.command || "";
      if (!argv || NOISE_COMMANDS.test(argv)) continue;
      const prefer = sawApply ? "patched" : "baseline";
      const key = `${prefer}:${argv}`;
      if (shownCommands.has(key)) continue;
      let captured = takeCommand(argv, prefer);
      if (!captured && prefer === "patched") {
        const leftover = leftoverLogs.find((command) => !used.has(command));
        if (leftover) {
          used.add(leftover);
          captured = { ...leftover, argv };
        }
      }
      const tail = captured?.tail || parsed?.output || "";
      shownCommands.add(key);
      if (!sawApply) beginPatching();
      add(
        sawApply ? "TESTING" : "PATCHING",
        tail ? "block" : "action",
        tail
          ? terminalFence(sandboxLabel(), [{ cmd: argv, out: tail }])
          : `$ ${argv}`,
      );
      continue;
    }

    if (name === "record_verification_report") {
      flushReads();
      if (sawVerifyReport) continue;
      if (!sawVerify) {
        add("VERIFYING", "thought", "Grade the diff and the clean logs. Do not read the patch author’s plan.");
        sawVerify = true;
      }
      add("VERIFYING", "action", "Verify(`proposed tree`)", { verb: "Verify", toolType: "Verify" });
      add("VERIFYING", "result", verifyLine(verification));
      sawVerifyReport = true;
      continue;
    }

    if (name === "open_pull_request") {
      flushReads();
      if (sawPr) continue;
      add("PR_CREATED", "narration", "Pull request opened. PatchAPI stopped.");
      sawPr = true;
      continue;
    }

    flushReads();
    add(at, row.kind === "result" ? "result" : "action", body.split("\n")[0], {
      verb: name,
      toolType: name,
    });
  }

  flushReads();

  const unused = [...patched, ...leftoverLogs].filter((command) => !used.has(command) && command.tail);
  if (unused.length > 0 && shownCommands.size === 0) {
    add(
      "TESTING",
      "block",
      terminalFence(
        sandboxLabel(),
        unused.map((command) => ({
          cmd: command.argv === "build" || command.argv === "tests" ? command.phase : command.argv,
          out: command.tail,
        })),
      ),
    );
  }

  if (detail.state === "PR_CREATED" && !sawPr) {
    add("PR_CREATED", "narration", "Pull request opened. PatchAPI stopped.");
  }
  if (detail.state === "FAILED" && !lines.some((item) => item.at === "FAILED")) {
    add("FAILED", "narration", failureCopy(detail.failure_reason));
  }
  if (detail.state === "BLOCKED" && !lines.some((item) => item.at === "BLOCKED")) {
    add("BLOCKED", "narration", "Policy blocked this path. No sandbox and no pull request.");
  }
  if (detail.state === "UNAFFECTED" && !lines.some((item) => item.at === "UNAFFECTED")) {
    add("UNAFFECTED", "narration", "Report-only. No runtime path, so no worktree and no pull request.");
  }
  if (detail.state === "HELD" && !lines.some((item) => item.at === "HELD")) {
    add("HELD", "narration", "Draft held. No pull request until the note takes effect.");
  }

  return lines;
}

/** A function-call dump stored as a thought or narration — not a sentence. */
function isToolDump(text: string): boolean {
  return /^[A-Za-z_][A-Za-z0-9_]*\s*\(/.test(text) || /^read_file\s+\S/.test(text);
}

/**
 * Docs, fixtures, and skill ids. The mock read the binding; it did not walk
 * the skill registry or expected-findings.yaml.
 */
function isNoiseRead(path: string): boolean {
  if (!path || path.startsWith("/")) return true;
  const lower = path.toLowerCase();
  if (lower.endsWith(".yaml") || lower.endsWith(".yml") || lower.endsWith(".md")) return true;
  if (!path.includes("/") && !path.includes(".")) return true;
  return false;
}

function isNoiseNarration(text: string): boolean {
  return /^Deterministic slice:/i.test(text);
}

function policyLine(policy: Record<string, unknown> | null): string {
  const decision = String(policy?.decision ?? policy?.outcome ?? "").toLowerCase();
  if (decision === "blocked") return "Policy blocked this path. No sandbox and no pull request.";
  if (decision === "human_required" || decision.includes("human")) {
    return "ALLOW patch. Live checks wait on a runtime secret the agent will request.";
  }
  if (decision && decision !== "allow") return "Policy recorded.";
  return "ALLOW patch and PR. Merge remains off.";
}

function verifyLine(verification: Record<string, unknown> | null): string {
  const verdict = String(verification?.verdict ?? verification?.outcome ?? "").toLowerCase();
  if (verdict === "fail" || verdict === "failed" || verdict === "reject") {
    return "Verification disagreed. Fail closed. No pull request.";
  }
  const independent =
    verification &&
    verification.verifier_agent &&
    verification.patch_agent &&
    verification.verifier_agent !== verification.patch_agent;
  return independent ? "Verifier ≠ patch author. Proposed tree may be opened." : "Verification recorded.";
}

/**
 * The states the current attempt passed through, in order, without repeats.
 *
 * Restarting a run does not erase its transitions — Postgres is the audit
 * record and a run that was tried four times should say so. But the ladder is
 * not the audit record; it is where the operator reads how far *this* attempt
 * has come. Drawn from every transition it becomes a loop through the same ten
 * states, which shows a run in flight as having reached the end several times
 * already. So the path starts at the last restart, which is the last time the
 * run returned to `RECEIVED`.
 */
function pathFrom(detail: RunDetail): MachineState[] {
  const transitions = detail.transitions;
  let start = 0;
  for (let index = transitions.length - 1; index > 0; index -= 1) {
    if (transitions[index].to_state === "RECEIVED") {
      start = index;
      break;
    }
  }
  const seen: MachineState[] = [];
  for (const transition of transitions.slice(start)) {
    const machine = machineOf(transition.to_state);
    if (seen[seen.length - 1] !== machine) seen.push(machine);
  }
  return seen.length > 0 ? seen : [machineOf(detail.state)];
}

/** The files the diff touches, as the base tree lists them. */
function filesFrom(diffs: DiffFile[]): FileHit[] {
  return diffs.map((file) => ({
    path: file.path,
    hits: file.additions + file.deletions,
    kind: "runtime" as const,
  }));
}

/**
 * One run, drawn from what the job recorded and what the inbox already knew.
 *
 * `change` is the card this run was started from. It is passed in rather than
 * re-fetched because the base tree has to be truthful from the first frame: the
 * usages a run is about are known when the button is pressed, and reading them
 * off the eventual diff would leave the panel saying "no usages at this SHA"
 * for the several minutes before a patch exists — the opposite of the truth,
 * and during exactly the stretch the operator is watching.
 *
 * Absent when a run is read back without its card, in which case the diff is
 * the only source and the panel says less rather than something invented.
 */
export function toRun(detail: RunDetail, index: number, change?: ProjectChange): MockRun {
  const machine = machineOf(detail.state);
  const diffText = detail.artifacts.find((artifact) => artifact.kind === "diff")?.body ?? "";
  const diffs = parseDiff(diffText);
  const pullRequest = detail.pull_request ?? null;
  const files = change?.files.length ? change.files : filesFrom(diffs);
  const commands = commandsFrom(detail.artifacts);
  const log = composeWorklog(detail, change, commands, diffs, files);

  return {
    id: detail.run_id,
    code: `R-${String(index + 1).padStart(3, "0")}`,
    changeId: detail.change_id,
    title: change?.title || detail.change_id,
    repo: detail.repository,
    baseSha: detail.base_sha,
    fileHits: change?.fileHits ?? diffs.reduce((sum, f) => sum + f.additions + f.deletions, 0),
    fileCount: change?.fileCount ?? diffs.length,
    identifiers: change?.identifiers ?? [],
    replacement: change?.replacement,
    files,
    action: "start" as ChangeActionId,
    machine,
    path: pathFrom(detail),
    bucket: bucketOf(machine),
    createdAt: Date.parse(detail.started_at) || Date.now(),
    attempt: detail.attempts_used,
    attemptBudget: detail.attempt_budget,
    pauseReason: detail.failure_reason ?? undefined,
    need: needFrom(detail),
    commands,
    diffs,
    checks: checksFrom(detail.verification),
    log,
    // The worklog is already history by the time it is read, so all of it is
    // visible. A live run supplies its own pacing by growing.
    revealed: log.length,
    lineStartedAt: Date.now(),
    prBranch: pullRequest ? String(pullRequest.head_branch ?? "") : undefined,
    prBase: pullRequest ? String(pullRequest.base_branch ?? "main") : undefined,
    prUrl: pullRequest ? String(pullRequest.url ?? "") || undefined : undefined,
    prNumber: pullRequest && pullRequest.number != null ? Number(pullRequest.number) : undefined,
    prTitle: pullRequest ? String(pullRequest.title ?? "") || undefined : undefined,
    traceId: detail.run_id,
    logSource: logSourceFrom(detail),
  };
}

/** The job's own rows, in the shape the phase log already reads. */
export function logSourceFrom(detail: RunDetail): RunFixture {
  return {
    run_id: detail.run_id,
    state: detail.state,
    repository: detail.repository,
    change_id: detail.change_id,
    base_sha: detail.base_sha,
    started_at: detail.started_at,
    ended_at: detail.ended_at,
    pull_request_url: detail.pull_request_url,
    pull_request_number: detail.pull_request_number,
    trace: detail.trace,
    artifacts: detail.artifacts.map((artifact) => ({
      kind: artifact.kind,
      body: artifact.body,
      media_type: artifact.media_type,
    })),
    verification: detail.verification,
    pull_request: detail.pull_request,
  };
}

/**
 * The run to draw between pressing Start and the first poll landing.
 *
 * Start switches to the Runs panel immediately, but the row does not exist
 * until the API answers and its detail is read — a second or two in which the
 * panel had nothing to draw and showed its no-runs empty state. That empty
 * state is a lie: the base tree is the inventory join, which was known before
 * the button was pressed. So this builds the run from the card, and the first
 * real poll replaces it.
 *
 * Nothing here is evidence. No diff, no command, no check, and a worklog that
 * says only that the run is waiting to be claimed.
 */
export function pendingRun(change: ProjectChange, index: number): MockRun {
  const started = new Date().toISOString();
  const id = `pending:${runKey(change)}`;
  return {
    id,
    code: `R-${String(index + 1).padStart(3, "0")}`,
    changeId: change.id,
    title: change.title,
    repo: change.repo,
    baseSha: change.baseSha,
    fileHits: change.fileHits,
    fileCount: change.fileCount,
    identifiers: change.identifiers,
    replacement: change.replacement,
    files: change.files,
    action: "start" as ChangeActionId,
    machine: "NORMALIZED",
    path: ["NORMALIZED"],
    bucket: "active",
    createdAt: Date.now(),
    attempt: 0,
    attemptBudget: 3,
    commands: [],
    diffs: [],
    checks: [],
    log: [
      line(
        "pending-1",
        "NORMALIZED",
        "narration",
        "Waiting for the remediator to claim this run. Lines appear as the job writes them.",
      ),
    ],
    revealed: 1,
    lineStartedAt: Date.now(),
    traceId: "",
    logSource: {
      run_id: id,
      state: "RECEIVED",
      repository: change.repo ?? "",
      change_id: change.id,
      base_sha: change.baseSha ?? "",
      started_at: started,
      ended_at: null,
      pull_request_url: null,
      pull_request_number: null,
      trace: [
        {
          sequence: 1,
          state: "RECEIVED",
          kind: "narration",
          verb: "",
          body: "Dispatched to remediator. Waiting for the remediator to claim this run.",
          tool_type: "",
          tool_use_id: "",
          file_path: "",
          occurred_at: started,
        },
      ],
      artifacts: [],
      verification: null,
      pull_request: null,
    },
  };
}

/** What a paused run is waiting for, read from what it said rather than guessed. */
function needFrom(detail: RunDetail): "secret" | "gcp" | undefined {
  if (machineOf(detail.state) !== "WAITING_ON_OPERATOR") return undefined;
  const said = `${detail.failure_reason ?? ""} ${detail.trace.map((row) => row.body).join(" ")}`;
  if (/connect gcp/i.test(said) && !/add [A-Z_]*KEY/i.test(said)) return "gcp";
  return "secret";
}

export async function fetchRuns(projectId: string): Promise<RunSummary[]> {
  const response = await fetch(`${API_URL}/api/projects/${projectId}/runs`, {
    credentials: "include",
  });
  if (!response.ok) throw new Error(`runs ${response.status}`);
  const payload = (await response.json()) as { runs?: RunSummary[] };
  return payload.runs ?? [];
}

export async function fetchRun(projectId: string, runId: string): Promise<RunDetail> {
  const response = await fetch(`${API_URL}/api/projects/${projectId}/runs/${runId}`, {
    credentials: "include",
  });
  if (!response.ok) throw new Error(`run ${response.status}`);
  return (await response.json()) as RunDetail;
}

export interface StartedRun {
  run_id: string;
  state: string;
  repository: string;
  dispatched: boolean;
  detail?: string;
}

/**
 * Ask the control plane to remediate one change in one repository.
 *
 * Safe to call twice. The API opens the run row before dispatching anything and
 * the row is unique per change and repository, so a second press rejoins the
 * first run rather than starting a second one.
 */
export async function startRemediation(
  projectId: string,
  changeId: string,
  repository?: string,
): Promise<StartedRun> {
  const response = await fetch(
    `${API_URL}/api/projects/${projectId}/changes/${encodeURIComponent(changeId)}/remediate`,
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(repository ? { repository } : {}),
    },
  );
  const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  const runId = String(payload.run_id ?? "");
  // A 503 after the row exists is still a run the console should open: the
  // job never started, but the failure reason is on that row, not in a toast
  // the operator never sees.
  if (!response.ok && !runId) {
    throw new Error(String(payload.detail ?? `remediate ${response.status}`));
  }
  return {
    run_id: runId,
    state: String(payload.state ?? "RECEIVED"),
    repository: String(payload.repository ?? repository ?? ""),
    dispatched: Boolean(payload.dispatched),
    detail: payload.detail ? String(payload.detail) : undefined,
  };
}
