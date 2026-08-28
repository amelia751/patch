/**
 * Does a resumed run read as one story, or as two?
 *
 * The complaint this answers: pressing Continue after connecting GCP looked
 * like the whole remediation started over. It partly did — a Cloud Run job
 * cannot outlive an operator hold, so the new execution re-clones the tree,
 * re-opens a sandbox and re-runs the deterministic scan, writing every setup
 * line a second time. The run is the same run; the worklog has to say so.
 *
 * Run it against a real run:
 *
 *   npx tsx scripts/check-resume-worklog.ts <run-detail.json>
 *
 * where the file is the body of `GET /api/projects/{id}/runs/{run_id}`. It
 * fails when the composed worklog repeats a line the operator has already read,
 * or when a resumed run does not say that it continued.
 */

import { readFileSync } from "node:fs";
import { composeWorklog } from "../src/components/interface/ops/changes-tab/live-runs";
import type { RunDetail } from "../src/components/interface/ops/changes-tab/live-runs";

const path = process.argv[2];
if (!path) {
  console.error("usage: check-resume-worklog.ts <run-detail.json>");
  process.exit(2);
}

const detail = JSON.parse(readFileSync(path, "utf8")) as RunDetail;
const lines = composeWorklog(detail, undefined, [], [], []);

const resumed = detail.trace.some((row) => /continuing this run/i.test(row.body ?? ""));
const seen = new Map<string, number>();
const repeats: string[] = [];
for (const line of lines) {
  const key = `${line.kind}:${line.text.trim().toLowerCase()}`;
  const count = (seen.get(key) ?? 0) + 1;
  seen.set(key, count);
  if (count === 2) repeats.push(line.text.split("\n")[0].slice(0, 100));
}

console.log(`run        ${detail.run_id}`);
console.log(`state      ${detail.state}`);
console.log(`traces     ${detail.trace.length} recorded`);
console.log(`worklog    ${lines.length} lines drawn`);
console.log(`resumed    ${resumed}`);

let failed = false;
if (repeats.length > 0) {
  failed = true;
  console.error(`\nFAIL: ${repeats.length} line(s) drawn twice — the run reads as a restart:`);
  for (const text of repeats) console.error(`  · ${text}`);
}
if (resumed && !lines.some((line) => /continuing this run/i.test(line.text))) {
  failed = true;
  console.error("\nFAIL: this run resumed, but the worklog never says it continued.");
}
if (failed) process.exit(1);

console.log("\nOK: every worklog line is written once, and a resumed run says it continued.");
