/** Max length stored/shown for thread titles (matches API / UI validation). */
export const MAX_THREAD_TITLE_LENGTH = 100;

/**
 * Use the first line of the user's message as a thread title (truncated).
 * Used for guest/local preview, SSE timeout fallback, and when the API sends
 * an explicit `title` on POST /api/threads (skips server-side title generation).
 */
export function deriveThreadTitleFromMessage(
  message: string,
  maxLen = MAX_THREAD_TITLE_LENGTH,
): string {
  const line = message.trim().split(/\r?\n/)[0]?.trim() ?? "";
  if (!line) return "";
  if (line.length <= maxLen) return line;
  return `${line.slice(0, Math.max(1, maxLen - 1))}…`;
}
