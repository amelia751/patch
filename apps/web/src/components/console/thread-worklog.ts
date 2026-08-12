import type { WorklogEntry } from "./thread-types";

export const wAction = (text: string, toolType?: string, toolUseId?: string, filePath?: string): WorklogEntry => ({ kind: "action", text, toolType, toolUseId, filePath });
export const wResult = (text: string, toolType?: string, toolUseId?: string): WorklogEntry => ({ kind: "result", text, toolType, toolUseId });
export const wNarration = (text: string): WorklogEntry => ({ kind: "narration", text });
export const wBlock = (text: string): WorklogEntry => ({ kind: "block", text });

const READ_TOOLS = new Set(["Read", "FileRead", "FileReadTool"]);
const SEARCH_TOOLS = new Set(["Grep", "GrepTool", "Glob", "GlobTool", "Search"]);
const COLLAPSIBLE_TOOLS = new Set([...READ_TOOLS, ...SEARCH_TOOLS]);

function isCollapsibleAction(entry: WorklogEntry): boolean {
  if (entry.kind !== "action" || !entry.toolType) return false;
  return COLLAPSIBLE_TOOLS.has(entry.toolType);
}

export function pairActionResults(entries: WorklogEntry[]): WorklogEntry[] {
  const actionsByUseId = new Map<string, number>();
  for (let i = 0; i < entries.length; i++) {
    const e = entries[i];
    if (e.kind === "action" && e.toolUseId) {
      actionsByUseId.set(e.toolUseId, i);
    }
  }
  const pairedResultIndices = new Set<number>();
  const paired = entries.map(e => ({ ...e }));
  for (let i = 0; i < entries.length; i++) {
    const e = entries[i];
    if (e.kind === "result" && e.toolUseId && actionsByUseId.has(e.toolUseId)) {
      const actionIdx = actionsByUseId.get(e.toolUseId)!;
      paired[actionIdx] = { ...paired[actionIdx], result: e.text };
      pairedResultIndices.add(i);
    }
  }
  return paired.filter((_, i) => !pairedResultIndices.has(i));
}

export function collapseWorklogEntries(entries: WorklogEntry[]): WorklogEntry[] {
  const result: WorklogEntry[] = [];
  let i = 0;
  while (i < entries.length) {
    if (!isCollapsibleAction(entries[i])) {
      result.push(entries[i]);
      i++;
      continue;
    }
    const groupStart = i;
    const items: { tool: string; detail: string }[] = [];
    while (i < entries.length && isCollapsibleAction(entries[i])) {
      items.push({ tool: entries[i].toolType!, detail: entries[i].text });
      i++;
      if (i < entries.length && entries[i].kind === "result") {
        i++;
      }
    }
    if (items.length < 3) {
      for (let j = groupStart; j < i; j++) {
        result.push(entries[j]);
      }
    } else {
      const reads = items.filter(it => READ_TOOLS.has(it.tool)).length;
      const searches = items.filter(it => SEARCH_TOOLS.has(it.tool)).length;
      const total = reads + searches;
      let label: string;
      if (searches > 0 && reads > 0) {
        label = `Explored ${total} file${total !== 1 ? "s" : ""}`;
      } else if (searches > 0) {
        label = `Explored ${searches} search${searches !== 1 ? "es" : ""}`;
      } else {
        label = `Read ${reads} file${reads !== 1 ? "s" : ""}`;
      }
      result.push({
        kind: "collapsed_group",
        text: label,
        toolType: reads >= searches ? "Read" : "Grep",
        items,
      });
    }
  }
  return result;
}
