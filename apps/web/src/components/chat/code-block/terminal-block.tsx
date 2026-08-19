"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { ChevronRight, Terminal, Copy, Check } from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { useSyntaxTheme, MONO_FONT } from "./syntax-theme";

interface TerminalBlockProps {
  code: string;
  onCopy?: (code: string) => void;
  className?: string;
}

/** Max output lines shown per command before capping */
const OUTPUT_CAP = 16;

interface ParsedCommand {
  command: string;
  output: string[];
}

/**
 * TerminalBlock — renders CLI commands each with their own expandable output.
 *
 * Expected format:
 *   # /working/dir           (optional)
 *   $ command one
 *   output line 1
 *   output line 2
 *   $ command two
 *   more output
 */
export function TerminalBlock({ code, onCopy, className }: TerminalBlockProps) {
  const [copied, setCopied] = useState(false);
  const { prismTheme } = useSyntaxTheme();

  const rawLines = code.split("\n");

  // Parse into individual commands with their output
  let workingDir = "";
  const commands: ParsedCommand[] = [];
  let current: ParsedCommand | null = null;

  for (const line of rawLines) {
    if (line.startsWith("# ") && commands.length === 0 && !current) {
      workingDir = line.substring(2);
    } else if (line.startsWith("$ ")) {
      if (current) commands.push(current);
      current = { command: line.substring(2), output: [] };
    } else if (current) {
      current.output.push(line);
    }
  }
  if (current) commands.push(current);

  // Fallback: if no commands parsed, show raw
  if (commands.length === 0) {
    commands.push({ command: rawLines.find(l => l.trim())?.replace(/^\$\s*/, "") || code, output: [] });
  }

  const handleCopy = () => {
    const cmdText = commands.map(c => c.command).join("\n");
    if (onCopy) onCopy(cmdText);
    else navigator.clipboard.writeText(cmdText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={cn("my-3 rounded-lg overflow-hidden border border-[var(--border-color)] max-w-full relative group not-prose", className)}>
      {/* Header */}
      <div className="bg-[var(--bg-tertiary)] px-3 py-1.5 flex items-center justify-between border-b border-[var(--border-color)]">
        <div className="flex items-center gap-2">
          <Terminal className="h-3 w-3 text-[var(--text-secondary)]" />
          <span className="text-xs text-[var(--text-secondary)]">Terminal</span>
          {workingDir && (
            <span className="text-[10px] text-[var(--text-secondary)] opacity-60 truncate max-w-[200px]">
              {workingDir}
            </span>
          )}
        </div>
        <button
          onClick={handleCopy}
          className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors opacity-0 group-hover:opacity-100"
        >
          {copied ? <Check className="h-2.5 w-2.5" /> : <Copy className="h-2.5 w-2.5" />}
        </button>
      </div>

      {/* Commands — each rendered separately */}
      <div className="bg-[var(--bg-secondary)]">
        {commands.map((cmd, idx) => (
          <CommandEntry
            key={idx}
            cmd={cmd}
            isLast={idx === commands.length - 1}
            prismTheme={prismTheme}
          />
        ))}
      </div>
    </div>
  );
}

/** Individual command with syntax-highlighted command line and expandable output */
function CommandEntry({
  cmd,
  isLast,
  prismTheme,
}: {
  cmd: ParsedCommand;
  isLast: boolean;
  prismTheme: Record<string, React.CSSProperties>;
}) {
  const [isExpanded, setIsExpanded] = useState(false);

  const hasOutput = cmd.output.length > 0;
  const isCapped = cmd.output.length > OUTPUT_CAP;

  // Detect language hint from command
  const lang = cmd.command.startsWith("powershell") || cmd.command.startsWith("pwsh")
    ? "powershell"
    : "bash";

  return (
    <div className={cn(!isLast && "border-b border-[var(--border-color)]")}>
      {/* Command line — syntax highlighted with expand icon on right */}
      <div
        className={cn(
          "flex items-start gap-0",
          hasOutput && "cursor-pointer hover:bg-[var(--bg-tertiary)] transition-colors"
        )}
        onClick={hasOutput ? () => setIsExpanded(!isExpanded) : undefined}
      >
        <span className="text-emerald-500 select-none flex-shrink-0 text-[11px] leading-[1.5] pl-3 py-1" style={{ fontFamily: MONO_FONT }}>$</span>
        <div className="flex-1 min-w-0 overflow-hidden">
          <SyntaxHighlighter
            language={lang}
            style={prismTheme}
            customStyle={{
              margin: 0,
              padding: "4px 8px",
              fontSize: "11px",
              lineHeight: "1.5",
              backgroundColor: "transparent",
              borderRadius: 0,
              overflow: "hidden",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontFamily: MONO_FONT,
            }}
            codeTagProps={{
              style: {
                fontFamily: MONO_FONT,
                fontSize: "11px",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word" as const,
              },
            }}
            wrapLines
            wrapLongLines
          >
            {cmd.command}
          </SyntaxHighlighter>
        </div>
        {hasOutput && (
          <ChevronRight
            className={cn(
              "h-3 w-3 text-[var(--text-secondary)] flex-shrink-0 mt-1.5 mr-3 transition-transform",
              isExpanded && "rotate-90"
            )}
          />
        )}
      </div>

      {/* Output — capped with expand */}
      {hasOutput && (isExpanded || cmd.output.length <= OUTPUT_CAP) && (
        <div className="px-3 pb-1">
          {(isExpanded ? cmd.output : cmd.output.slice(0, OUTPUT_CAP)).map((line, idx) => (
            <div
              key={idx}
              className={cn(
                "text-[11px] whitespace-pre-wrap break-all leading-[1.5]",
                /^exited \d+/.test(line)
                  ? "text-[var(--text-secondary)]/50"
                  : "text-[var(--text-secondary)]",
              )}
              style={{ fontFamily: MONO_FONT }}
            >
              {line || " "}
            </div>
          ))}
          {isCapped && isExpanded && (
            <div className="text-[10px] text-[var(--text-secondary)] opacity-50 mt-0.5">
              {cmd.output.length} lines total
            </div>
          )}
        </div>
      )}

      {/* Collapsed preview — show first OUTPUT_CAP lines when not expanded and has more */}
      {hasOutput && !isExpanded && cmd.output.length > OUTPUT_CAP && (
        <div className="px-3 pb-1">
          {cmd.output.slice(0, OUTPUT_CAP).map((line, idx) => (
            <div
              key={idx}
              className="text-[var(--text-secondary)] text-[11px] whitespace-pre-wrap break-all leading-[1.5] opacity-60"
              style={{ fontFamily: MONO_FONT }}
            >
              {line || " "}
            </div>
          ))}
          <div className="text-[10px] text-[var(--text-secondary)] opacity-50 mt-0.5">
            +{cmd.output.length - OUTPUT_CAP} more lines
          </div>
        </div>
      )}
    </div>
  );
}
