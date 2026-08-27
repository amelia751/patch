/**
 * Real runs, in the shape the runs panel already draws.
 *
 * The panel was built against `run-scripts`, a fixture that walked a scripted
 * ladder on a timer. Everything it renders — the three trees, the worklog, the
 * sandbox commands, the verification checks — now exists for real: the
 * remediation job writes each of them to Postgres as it happens, and the run
 * API serves them. What was missing was the translation, so this is only that.
 *
 * Keeping `MockRun` as the target type is deliberate. The panel's vocabulary is
 * good and the alternative — reshaping several hundred lines of rendering to
 * match the wire format — would risk the UI to gain nothing a mapper does not.
 *
 * Nothing here invents a value. A run with no diff yet has no diff; a check
 * that has not run is absent rather than pending-and-green. The panel is
 * showing evidence, and an empty section is the honest rendering of a stage the
 * run has not reached.
 */

import type { ChangeActionId } from "./actions";
import type { FileHit, ProjectChange } from "./data";
import type {
  AgentLogLine,
  DiffFile,
  DiffLine,
  LogKind,
  MachineState,
  MockRun,
  RunBucket,
  SandboxCommand,
  VerifyCheck,
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

function checksFrom(verification: Record<string, unknown> | null): VerifyCheck[] {
  const raw = verification?.checks;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    .map((item) => ({
      name: String(item.name ?? ""),
      passed: Boolean(item.passed),
    }))
    .filter((check) => check.name);
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

function parseToolCall(body: string): { name: string; args: Record<string, string>; output: string } | null {
  const raw = body.trim();
  const arrow = raw.indexOf(" → ");
  const newline = raw.indexOf("\n");
  const head = arrow >= 0 ? raw.slice(0, arrow) : newline >= 0 ? raw.split("\n")[0] : raw;
  const output = newline >= 0 ? raw.slice(newline + 1).trim() : "";
  const match = head.replace(/\s*→\s*[\s\S]*$/, "").match(/^([A-Za-z_][A-Za-z0-9_]*)\((.*)\)\s*$/);
  if (!match) return null;
  return { name: match[1], args: namedArgs(match[2]), output };
}

const HIDDEN_TOOLS = new Set([
  "computer_use_step",
  "list_verification_evidence",
  "list_dir",
  "list_runtime_credentials",
  "record_patch_plan",
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
 * Rebuild the mock's worklog shape from what the job actually recorded.
 *
 * The fixture was a story: a thought, a named tool, a one-line result, a
 * terminal with captured stdout. The job writes ADK tool names and, until
 * this change, summarised results as `{keys}`. Thoughts from Gemini were
 * dropped. This composer does not invent a thought the model did not say
 * and does not invent stdout — it uses the product's recorded stage facts
 * (policy reason, verification notes, pinned SHA, artifact logs) and the
 * same sentences the fixture used when those facts are present.
 */
function composeWorklog(
  detail: RunDetail,
  change: ProjectChange | undefined,
  commands: SandboxCommand[],
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

  const repo = detail.repository;
  const sha = detail.base_sha.slice(0, 12) || "unpinned";
  const identifier = change?.identifiers[0] ?? "";
  const policy = detail.policy;
  const verification = detail.verification;
  const baseline = commands.filter((command) => command.source === "baseline" && command.argv !== "build" && command.argv !== "tests");
  const patched = commands.filter((command) => command.source !== "baseline" && command.argv !== "build" && command.argv !== "tests");
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
  let sawPatch = false;
  let sawVerify = false;
  let sawVerifyReport = false;
  let sawApply = false;
  const shownCommands = new Set<string>();
  const pendingReads: { path: string; at: MachineState }[] = [];

  const flushReads = (at: MachineState) => {
    for (const read of pendingReads) {
      add(read.at, "action", `Read(\`${read.path}\`)`, {
        verb: "Read",
        toolType: "Read",
        filePath: read.path,
      });
    }
    pendingReads.length = 0;
    if (at === "IMPACT_SCANNING" && !sawImpact) {
      const hits = change?.fileHits;
      const files = change?.files.filter((file) => file.kind === "runtime").length ?? change?.fileCount;
      if (hits != null && files != null) {
        add(at, "result", `${hits} hits · ${files} runtime paths.`);
      }
      sawImpact = true;
    }
  };

  for (const row of detail.trace) {
    const at = machineOf(row.state);
    if (row.kind === "thought" && row.body.trim()) {
      flushReads(at);
      add(at, "thought", row.body.trim());
      continue;
    }
    if (row.kind === "narration" && row.body.trim()) {
      flushReads(at);
      add(at, "narration", row.body.trim());
      continue;
    }

    const parsed = parseToolCall(row.body);
    const name = parsed?.name || row.verb;
    if (!name || HIDDEN_TOOLS.has(name)) continue;

    if (name === "seed_static_manifest") {
      if (!sawNormalize) {
        add("NORMALIZED", "thought", "Provider text is untrusted. Screen it before anything joins inventory.");
        add("NORMALIZED", "action", "Normalize(`ChangeManifest`)", {
          verb: "Normalize",
          toolType: "Normalize",
        });
        add("NORMALIZED", "result", "Identifiers kept as claims.");
        sawNormalize = true;
      }
      continue;
    }

    if (name === "scan_repository") {
      if (identifier) {
        add("IMPACT_SCANNING", "thought", `Join \`${identifier}\` against ${repo} @ ${sha}, not HEAD.`);
      }
      add("IMPACT_SCANNING", "action", "Search(`inventory`)", { verb: "Search", toolType: "Grep" });
      continue;
    }

    if (name === "read_file" || name === "read_verification_evidence" || name === "load_migration_skill") {
      const path = workspacePath(
        row.file_path || parsed?.args.path || parsed?.args.name || parsed?.args.skill_id || "",
      );
      if (!path || path.startsWith("/")) continue;
      if (name === "read_verification_evidence" && !sawVerify) {
        add("VERIFYING", "thought", "Grade the diff and the clean logs. Do not read the patch author’s plan.");
        sawVerify = true;
      }
      const stage =
        name === "read_verification_evidence"
          ? "VERIFYING"
          : sawApply
            ? at
            : !sawPatch
              ? "PATCHING"
              : at;
      if (stage === "PATCHING" && !sawPatch) {
        add("PATCHING", "thought", "Read the binding at the pinned SHA before rewriting.");
        sawPatch = true;
      }
      pendingReads.push({ path, at: machineOf(stage) });
      continue;
    }

    if (name === "record_impact_report") {
      flushReads("IMPACT_SCANNING");
      continue;
    }

    if (name === "evaluate_policy" || name === "record_policy_decision") {
      flushReads("IMPACT_SCANNING");
      if (sawPolicy) continue;
      add("POLICY_EVALUATION", "narration", "Auto-merge stays false. Forbidden paths stay forbidden.");
      add("POLICY_EVALUATION", "action", "Evaluate(`impact report`)", {
        verb: "Evaluate",
        toolType: "Evaluate",
      });
      const reason = typeof policy?.reason === "string" ? policy.reason : "";
      const decision = String(policy?.decision ?? "");
      add(
        "POLICY_EVALUATION",
        "result",
        reason ||
          (decision && decision !== "human_required"
            ? "ALLOW patch and PR. Merge remains off."
            : "Policy recorded."),
      );
      sawPolicy = true;
      continue;
    }

    if (name === "apply_patch") {
      flushReads("PATCHING");
      const files = parsed?.args.files || parsed?.args.path || "apply_patch";
      add("PATCHING", "action", `Edit(\`${workspacePath(files)}\`)`, {
        verb: "Apply",
        toolType: "Edit",
      });
      sawApply = true;
      continue;
    }

    if (name === "run_command") {
      flushReads(at);
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
      if (!tail) continue;
      shownCommands.add(key);
      add(
        sawApply ? "TESTING" : "PATCHING",
        "block",
        terminalFence("/tmp/patchapi-sandbox", [{ cmd: argv, out: tail }]),
      );
      continue;
    }

    if (name === "record_verification_report") {
      flushReads("VERIFYING");
      if (sawVerifyReport) continue;
      if (!sawVerify) {
        add("VERIFYING", "thought", "Grade the diff and the clean logs. Do not read the patch author’s plan.");
        sawVerify = true;
      }
      add("VERIFYING", "action", "Verify(`proposed tree`)", { verb: "Verify", toolType: "Verify" });
      const independent =
        verification &&
        verification.verifier_agent &&
        verification.patch_agent &&
        verification.verifier_agent !== verification.patch_agent;
      const notes = typeof verification?.evidence_summary === "string" ? verification.evidence_summary : "";
      add(
        "VERIFYING",
        "result",
        notes || (independent ? "Verifier ≠ patch author. Proposed tree may be opened." : "Verification recorded."),
      );
      sawVerifyReport = true;
      continue;
    }

    if (name === "open_pull_request") {
      flushReads(at);
      add("PR_CREATED", "narration", "Pull request opened. PatchAPI stopped.");
      continue;
    }
  }

  flushReads(machineOf(detail.state));

  const unused = [...patched, ...leftoverLogs].filter((command) => !used.has(command) && command.tail);
  if (unused.length > 0 && shownCommands.size === 0) {
    add(
      "TESTING",
      "block",
      terminalFence(
        "/tmp/patchapi-sandbox",
        unused.map((command) => ({
          cmd: command.argv === "build" || command.argv === "tests" ? command.phase : command.argv,
          out: command.tail,
        })),
      ),
    );
  }

  if (detail.state === "PR_CREATED" && !lines.some((item) => item.at === "PR_CREATED")) {
    add("PR_CREATED", "narration", "Pull request opened. PatchAPI stopped.");
  }

  return lines;
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
    log: composeWorklog(detail, change, commands),
    // The worklog is already history by the time it is read, so all of it is
    // visible. The fixture revealed lines on a timer to imitate a run in
    // progress; a real run supplies its own pacing by growing.
    revealed: detail.trace.length,
    lineStartedAt: Date.now(),
    prBranch: pullRequest ? String(pullRequest.head_branch ?? "") : undefined,
    traceId: detail.run_id,
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
  if (!response.ok) {
    throw new Error(String(payload.detail ?? `remediate ${response.status}`));
  }
  return {
    run_id: String(payload.run_id ?? ""),
    state: String(payload.state ?? "RECEIVED"),
    repository: String(payload.repository ?? repository ?? ""),
    dispatched: Boolean(payload.dispatched),
    detail: payload.detail ? String(payload.detail) : undefined,
  };
}
