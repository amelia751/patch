import type { ThreadEvent } from "./thread-types";

/**
 * Format task events into markdown content for display.
 *
 * Handles events from the backend:
 * - thinking: Agent reasoning (collapsible gray section)
 * - file_create: File written with syntax highlighting
 * - code_diff: File edit with diff view
 * - cli_command: Terminal command execution
 * - cli_output: Command stdout/stderr streaming
 * - cli_complete: Command finished with exit code
 * - tool_result: Tool execution result
 * - resource_create: Cloud resource being created
 * - resource_verify: Cloud resource verified
 * - success/failure: Completion status
 *
 * Legacy types for backwards compatibility:
 * - thought, action, code_generated, command_run, resource_created, progress
 */
export function formatTaskEvents(events: ThreadEvent[]): string {
  const lines: string[] = [];

  for (const event of events) {
    const type = event.type;
    const content = event.content;
    const metadata = event.metadata || {};

    if (type === "thinking") {
      continue;
    }
    else if (type === "planning") {
      const desc = typeof content === "object" ? content?.description : "";
      const steps = typeof content === "object" ? content?.steps || [] : [];
      if (desc) {
        lines.push(`**${desc}**\n\n`);
      }
      steps.forEach((step: string, i: number) => {
        lines.push(`${i + 1}. ${step}\n`);
      });
      lines.push("\n");
    }
    else if (type === "file_create") {
      const filename = typeof content === "object" ? content?.filename : metadata?.filename || "";
      const fileContent = typeof content === "object" ? content?.content : content || "";
      const desc = typeof content === "object" ? content?.description : "";

      if (desc) {
        lines.push(`${desc}\n\n`);
      }

      const normalizedPath = (filename || "").replace(/\\/g, '/');
      const shortPath = normalizedPath.split('/').slice(-3).join('/');

      if (fileContent) {
        const contentLines = fileContent.split('\n');
        const displayLines = contentLines.slice(0, 30);
        const diffContent = displayLines.map((l: string) => `+${l}`).join('\n');
        const truncation = contentLines.length > 30 ? `\n+... ${contentLines.length - 30} more lines` : '';
        lines.push(`\`\`\`diff\n--- /dev/null\n+++ b/${shortPath}\n${diffContent}${truncation}\n\`\`\`\n\n`);
      } else {
        lines.push(`\`${shortPath}\`\n\n`);
      }
    }
    else if (type === "code_diff") {
      const filename = typeof content === "object" ? content?.filename : metadata?.filename || "";
      const description = typeof content === "object" ? content?.description : "";
      const oldContent = typeof content === "object" ? content?.old : "";
      const newContent = typeof content === "object" ? content?.new : "";

      if (description) {
        lines.push(`${description}\n\n`);
      }
      const normalizedPath = (filename || "").replace(/\\/g, '/');
      const shortPath = normalizedPath.split('/').slice(-3).join('/');
      const removedLines = (oldContent || "").split("\n").map((l: string) => `-${l}`).join("\n");
      const addedLines = (newContent || "").split("\n").map((l: string) => `+${l}`).join("\n");
      lines.push(`\`\`\`diff\n--- a/${shortPath}\n+++ b/${shortPath}\n${removedLines}\n${addedLines}\n\`\`\`\n\n`);
    }
    else if (type === "cli_command") {
      const cmd = typeof content === "object" ? content?.command : content || "";
      const workingDir = typeof content === "object" ? content?.working_dir : "";

      if (workingDir) {
        lines.push(`\`\`\`terminal\n# ${workingDir}\n$ ${cmd}\n`);
      } else {
        lines.push(`\`\`\`terminal\n$ ${cmd}\n`);
      }
    }
    else if (type === "cli_output") {
      const output = typeof content === "object" ? content?.output : content || "";
      const stream = typeof content === "object" ? content?.stream : "stdout";

      if (stream === "stderr") {
        lines.push(`${output} # stderr\n`);
      } else {
        lines.push(`${output}\n`);
      }
    }
    else if (type === "cli_complete") {
      const exitCode = typeof content === "object" ? content?.exit_code : content;
      const success = typeof content === "object" ? content?.success : (exitCode === 0);

      lines.push(`\`\`\`\n`);
      if (success) {
        lines.push(`✓ Command completed successfully\n\n`);
      } else {
        lines.push(`✗ Command failed (exit code ${exitCode})\n\n`);
      }
    }
    else if (type === "tool_result") {
      const tool = typeof content === "object" ? content?.tool : "";
      const result = typeof content === "object" ? content?.result : content;
      const success = typeof content === "object" ? content?.success : true;
      const error = typeof content === "object" ? content?.error : "";

      if (success) {
        lines.push(`✓ ${tool}: ${typeof result === "string" ? result : JSON.stringify(result)}\n\n`);
      } else {
        lines.push(`✗ ${tool}: ${error || "Failed"}\n\n`);
      }
    }
    else if (type === "resource_create" || type === "resource_creating") {
      const resourceType = typeof content === "object" ? content?.resource_type : metadata?.resource_type || "";
      const name = typeof content === "object" ? content?.name : metadata?.name || "";
      lines.push(`Creating ${resourceType}: **${name}**\n\n`);
    }
    else if (type === "resource_verify" || type === "resource_verified") {
      const resourceType = typeof content === "object" ? content?.resource_type : metadata?.resource_type || "";
      const name = typeof content === "object" ? content?.name : metadata?.name || "";
      const arn = typeof content === "object" ? content?.arn : metadata?.arn || "";
      lines.push(`✓ Created ${resourceType}: **${name}**`);
      if (arn) {
        lines.push(` \`${arn}\``);
      }
      lines.push(`\n\n`);
    }
    else if (type === "success") {
      const msg = typeof content === "string" ? content : content?.message || "Completed";
      if (!msg || /^(completed|finished|success)$/i.test(String(msg).trim())) {
        continue;
      }
      lines.push(`\n✓ **${msg}**\n\n`);
    }
    else if (type === "failure") {
      const msg = typeof content === "string" ? content : content?.message || "Failed";
      lines.push(`\n✗ **${msg}**\n\n`);
    }
    else if (type === "warning") {
      const msg = typeof content === "string" ? content : content?.message || "";
      lines.push(`${msg}\n\n`);
    }
    else if (type === "error") {
      const msg = typeof content === "object" ? content?.message : content || "";
      lines.push(`✗ **Error:** ${msg}\n\n`);
    }
    else if (type === "phase") {
      const name = typeof content === "object" ? content?.name : content || "";
      const desc = typeof content === "object" ? content?.description : "";
      lines.push(`**${name}**`);
      if (desc) {
        lines.push(`: ${desc}`);
      }
      lines.push(`\n\n`);
    }
    else if (type === "progress") {
      const current = typeof content === "object" ? content?.current : metadata?.current;
      const total = typeof content === "object" ? content?.total : metadata?.total;
      const msg = typeof content === "object" ? content?.message : content || "";
      if (current !== undefined && total !== undefined) {
        lines.push(`[${current}/${total}] ${msg}\n\n`);
      } else if (msg) {
        lines.push(`${msg}\n\n`);
      }
    }
    else if (type === "message") {
      const msg = typeof content === "string" ? content : content?.message || "";
      if (msg) {
        lines.push(`${msg}\n\n`);
      }
    }

    // === LEGACY EVENT TYPES (backwards compatibility) ===

    else if (type === "thought") {
      continue;
    }
    else if (type === "action") {
      const text = typeof content === "string" ? content :
                   (content?.action || content?.message || content?.content || JSON.stringify(content));
      lines.push(`${text}\n\n`);
    }
    else if (type === "code_generated") {
      const code = typeof content === "string" ? content : (content?.code || JSON.stringify(content));
      if (metadata.filename) {
        const normalizedPath = metadata.filename.replace(/\\/g, '/');
        const shortPath = normalizedPath.split('/').slice(-3).join('/');
        const contentLines = code.split('\n');
        const displayLines = contentLines.slice(0, 30);
        const diffContent = displayLines.map((l: string) => `+${l}`).join('\n');
        const truncation = contentLines.length > 30 ? `\n+... ${contentLines.length - 30} more lines` : '';
        lines.push(`\`\`\`diff\n--- /dev/null\n+++ b/${shortPath}\n${diffContent}${truncation}\n\`\`\`\n\n`);
      } else {
        const lang = metadata.language || "text";
        lines.push(`\n\`\`\`${lang}\n${code}\n\`\`\`\n\n`);
      }
    }
    else if (type === "command_run") {
      const cmd = metadata.command || (typeof content === "string" ? content : content?.command || "");
      lines.push(`\n\`\`\`terminal\n$ ${cmd}\n`);
      if (metadata.output) {
        lines.push(`${metadata.output}\n`);
      }
      lines.push(`\`\`\`\n\n`);
    }
    else if (type === "resource_created") {
      lines.push(`✓ ${metadata.resource_type}: ${metadata.resource_name}`);
      if (metadata.arn) {
        lines.push(` (${metadata.arn})`);
      }
      lines.push(`\n\n`);
    }
    else if (type === "code_block") {
      const code = typeof content === "object" ? content?.code : content;
      const lang = typeof content === "object" ? content?.language : metadata?.language || "text";
      const filename = typeof content === "object" ? content?.filename : metadata?.filename;
      if (filename) {
        lines.push(`**${filename}**\n\n`);
      }
      lines.push(`\`\`\`${lang}\n${code}\n\`\`\`\n\n`);
    }
    else if (content) {
      const textContent = typeof content === "string" ? content :
                          (content?.message || content?.content || content?.text || JSON.stringify(content));
      lines.push(`${textContent}\n\n`);
    }
  }

  return lines.join("");
}
