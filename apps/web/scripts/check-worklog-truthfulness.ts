/**
 * Does the console only assert what the run actually did?
 *
 * Three fabrications this catches, all found in one real run:
 *
 *  1. An `apply_patch` that was rejected ("patch does not apply") was drawn as
 *     a successful Edit, because a result with no diff of its own fell through
 *     to the run's *final* diff artifact. The rejected attempt was credited
 *     with the change its retry made.
 *  2. Every patched file was therefore drawn twice — once for the failed
 *     attempt, once for the one that applied.
 *  3. Terminal fences were headed `/tmp/patchapi-sandbox`, a path nothing ran
 *     in. A GKE sandbox executes in its own container.
 *
 * Run it against a real run:
 *
 *   npx tsx scripts/check-worklog-truthfulness.ts <run-detail.json>
 *
 * where the file is the body of `GET /api/projects/{id}/runs/{run_id}`.
 */

import { readFileSync } from "node:fs";
import { composeWorklog, parseDiff, toRun } from "../src/components/interface/ops/changes-tab/live-runs";
import type { RunDetail } from "../src/components/interface/ops/changes-tab/live-runs";
import { proposedPending, treeAvailable } from "../src/components/interface/ops/changes-tab/run-scripts";

const path = process.argv[2];
if (!path) {
  console.error("usage: check-worklog-truthfulness.ts <run-detail.json>");
  process.exit(2);
}

const detail = JSON.parse(readFileSync(path, "utf8")) as RunDetail;
const diffText = detail.artifacts.find((artifact) => artifact.kind === "diff")?.body ?? "";
const lines = composeWorklog(detail, undefined, [], parseDiff(diffText), []);
const run = toRun(detail, 0);

const failures: string[] = [];

// 1. A rejected apply_patch must not be drawn with a diff.
const rejected = detail.trace.filter(
  (row) => /^apply_patch\(/.test((row.body ?? "").trim()) && /does not apply|^.*→\s*error/i.test(row.body ?? ""),
);
for (const [index, entry] of lines.entries()) {
  if (entry.kind !== "action" || !/^Edit\(|^Write\(/.test(entry.text)) continue;
  const next = lines[index + 1];
  const drewDiff = next?.kind === "block" && next.text.includes("diff --git");
  const saidRefused = lines[index + 1]?.kind === "result" && /does not apply|error/i.test(lines[index + 1].text);
  if (drewDiff && saidRefused) failures.push(`edit drawn with both a diff and a refusal: ${entry.text}`);
}

// 2. No file's edit block may be drawn twice with the same diff.
const drawn = new Map<string, number>();
for (const [index, entry] of lines.entries()) {
  if (entry.kind !== "action" || !/^Edit\(|^Write\(/.test(entry.text)) continue;
  const block = lines[index + 1];
  if (block?.kind !== "block") continue;
  const key = `${entry.text}::${block.text}`;
  const seen = (drawn.get(key) ?? 0) + 1;
  drawn.set(key, seen);
  if (seen === 2) failures.push(`edit drawn twice with an identical diff: ${entry.text}`);
}

// 3. No fabricated working directory.
for (const entry of lines) {
  if (entry.text.includes("/tmp/patchapi-sandbox")) {
    failures.push(`terminal claims a path nothing ran in: ${entry.text.split("\n")[1] ?? entry.text}`);
  }
}

const editCount = lines.filter((l) => l.kind === "action" && /^Edit\(|^Write\(/.test(l.text)).length;

console.log(`run            ${detail.run_id}`);
console.log(`state          ${detail.state}`);
console.log(`traces         ${detail.trace.length}`);
console.log(`worklog        ${lines.length} lines`);
console.log(`apply_patch    ${detail.trace.filter((r) => /^apply_patch\(/.test((r.body ?? "").trim())).length} calls, ${rejected.length} rejected`);
console.log(`edits drawn    ${editCount}`);
console.log(`sandbox chip   ${treeAvailable(run, "sandbox") ? "worktree" : "not allocated"}`);
console.log(`proposed chip  ${treeAvailable(run, "proposed") && run.prBranch ? run.prBranch : proposedPending(run)}`);

if (failures.length > 0) {
  console.error(`\nFAIL: the console asserts ${failures.length} thing(s) the run did not do:`);
  for (const text of failures) console.error(`  · ${text}`);
  process.exit(1);
}
console.log("\nOK: no rejected patch drawn as an edit, no edit drawn twice, no invented path.");
