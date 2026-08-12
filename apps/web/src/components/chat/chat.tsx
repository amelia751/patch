"use client";

import { useState, useEffect, useRef, useLayoutEffect } from "react";
import {
  Send,
  ThumbsUp,
  ThumbsDown,
  Copy,
  RotateCw,
  Paperclip
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useArchitecture, CheckpointInfo, ClarificationInfo } from "@/lib/architecture-context";
import { ActionMessage } from "./action-message";
import { ClarificationCard } from "./clarification-card";
import { DiffBlock, CodeBlock } from "./code-block";

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: Date;
  type?: "normal" | "clarification" | "checkpoint" | "approved" | "error" | "action";
  metadata?: {
    clarification?: ClarificationInfo;
    checkpoint?: CheckpointInfo;
    sectionStates?: Record<string, string>;
    phase?: string;
    actionText?: string;
    actionDuration?: string;
  };
}

export function Chat() {
  const { state, sendMessage } = useArchitecture();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [showThinking, setShowThinking] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [actionMessages, setActionMessages] = useState<string[]>([]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming, streamingText, actionMessages]);

  // Initialize with welcome message
  useEffect(() => {
    if (!demoMode) {
      setMessages([
        {
          id: "welcome",
          role: "assistant",
          content: "To get started, import a project from GitHub.\n\nOnce your project is connected, I'll help you shape and ship production-ready infrastructure by generating:\n- API endpoints and auth rules\n- Tests and verification plans\n- Deployable backend architecture\n- Integration guidance for frontend tools",
          timestamp: new Date(),
          type: "normal",
        },
      ]);
    }
  }, [demoMode]);

  // Demo flow function
  const startDemoFlow = async () => {
    setDemoMode(true);
    setMessages([]);
    setActionMessages([]);

    // Step 1: User message
    await new Promise(resolve => setTimeout(resolve, 500));
    setMessages([{
      id: "demo-1",
      role: "user",
      content: "Analyze my e-commerce application and design the AWS infrastructure",
      timestamp: new Date(),
      type: "normal",
    }]);

    // Step 2: Show thinking with duration
    const thinkStart = Date.now();
    await new Promise(resolve => setTimeout(resolve, 400));
    setShowThinking(true);

    // Step 3: Show thinking completion
    await new Promise(resolve => setTimeout(resolve, 800));
    setShowThinking(false);
    const thinkDuration = ((Date.now() - thinkStart) / 1000).toFixed(1);
    setMessages(prev => [...prev, {
      id: "action-thought",
      role: "assistant",
      content: "",
      timestamp: new Date(),
      type: "action",
      metadata: {
        actionText: "Thought",
        actionDuration: `${thinkDuration}s`
      }
    }]);

    // Step 4: Progressive exploration actions
    await new Promise(resolve => setTimeout(resolve, 400));
    setMessages(prev => [...prev, {
      id: "action-explore-1",
      role: "assistant",
      content: "",
      timestamp: new Date(),
      type: "action",
      metadata: {
        actionText: "Explored 1 file",
        actionDuration: "0.4s"
      }
    }]);

    await new Promise(resolve => setTimeout(resolve, 300));
    setMessages(prev => [...prev, {
      id: "action-explore-2",
      role: "assistant",
      content: "",
      timestamp: new Date(),
      type: "action",
      metadata: {
        actionText: "Explored 3 searches",
        actionDuration: "0.3s"
      }
    }]);

    // Step 5: Stream response (muted, longer content)
    await new Promise(resolve => setTimeout(resolve, 400));
    const fullResponse = "I'll analyze your e-commerce application and design a production-ready AWS infrastructure.\n\nBased on examining your Next.js application structure, authentication patterns, and data models, I'll create a serverless architecture optimized for scalability and cost efficiency.\n\nKey components identified:\n• React 19 frontend with TypeScript\n• Server-side rendering with API routes\n• User authentication system\n• Real-time data synchronization needs\n• File upload capabilities for product images";
    setIsStreaming(true);

    for (let i = 0; i <= fullResponse.length; i++) {
      setStreamingText(fullResponse.slice(0, i));
      await new Promise(resolve => setTimeout(resolve, 12));
    }

    // Clear streaming and add final message
    await new Promise(resolve => setTimeout(resolve, 300));
    setIsStreaming(false);
    setStreamingText("");

    setMessages(prev => [...prev, {
      id: "demo-2",
      role: "assistant",
      content: "I've analyzed your application structure and identified the key components.\n\nBased on the codebase, I'll design an AWS infrastructure that supports:\n\n• **Frontend**: Next.js application with CloudFront CDN\n• **Backend**: Serverless API with Lambda + API Gateway  \n• **Database**: DynamoDB for session/user data\n• **Authentication**: Cognito for user management\n• **File Storage**: S3 for static assets\n• **Real-time**: WebSocket API for live updates",
      timestamp: new Date(),
      type: "normal",
    }]);

    // Step 6: Show code with diff
    await new Promise(resolve => setTimeout(resolve, 1000));
    setShowThinking(true);
    setActionMessages(["Writing to architecture-context.tsx"]);

    await new Promise(resolve => setTimeout(resolve, 1200));
    setShowThinking(false);
    setActionMessages([]);

    setMessages(prev => [...prev, {
      id: "action-edit-1",
      role: "assistant",
      content: "",
      timestamp: new Date(),
      type: "action",
      metadata: {
        actionText: "Edited 1 file",
        actionDuration: "1.2s"
      }
    }, {
      id: "demo-3",
      role: "assistant",
      content: "Here's the authentication fix I applied:\n\n```diff\n--- apps/web/src/lib/architecture-context.tsx\n+++ apps/web/src/lib/architecture-context.tsx\n@@ -1,5 +1,6 @@\n import React, { createContext, useContext, useState, useCallback, useEffect } from \"react\";\n+import { useAuth } from \"./auth-context\";\n \n export function ArchitectureProvider({ children }: { children: React.ReactNode }) {\n   const [state, setState] = useState<ArchitectureState>(initialState);\n+  const { isAuthenticated } = useAuth();\n \n+  // Clear architecture when user logs out\n+  useEffect(() => {\n+    if (!isAuthenticated) {\n+      setState(initialState);\n+    }\n+  }, [isAuthenticated]);\n```\n\nAnd tested it:\n\n```bash\n$ cd services/orchestrator && source venv/bin/activate\n$ python -m uvicorn app.main:app --reload --port 8000\n\nINFO:     Will watch for changes in these directories: ['/Users/anhlam/patchapi/services/orchestrator']\nINFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)\nINFO:     Started reloader process [28934] using WatchFiles\nINFO:     Started server process [28936]\nINFO:     Waiting for application startup.\nINFO:     Application startup complete.\n```",
      timestamp: new Date(),
      type: "normal",
    }]);

    // Step 7: Show diff with deletions only
    await new Promise(resolve => setTimeout(resolve, 900));
    setMessages(prev => [...prev, {
      id: "demo-3b",
      role: "assistant",
      content: "I removed the deprecated polling logic:\n\n```diff\n--- apps/web/src/lib/api-client.ts\n+++ apps/web/src/lib/api-client.ts\n@@ -45,23 +45,6 @@\n   return response.json();\n }\n \n-// Deprecated: Use WebSocket connection instead\n-export async function pollForUpdates(resourceId: string) {\n-  const interval = setInterval(async () => {\n-    try {\n-      const response = await fetch(`${API_URL}/resources/${resourceId}`);\n-      const data = await response.json();\n-      console.log('Polling update:', data);\n-    } catch (error) {\n-      console.error('Polling failed:', error);\n-    }\n-  }, 5000);\n-  \n-  return () => clearInterval(interval);\n-}\n-\n export function connectWebSocket(url: string) {\n   const ws = new WebSocket(url);\n   return ws;\n```",
      timestamp: new Date(),
      type: "normal",
    }]);

    // Step 8: Show diff with both additions and deletions
    await new Promise(resolve => setTimeout(resolve, 1000));
    setMessages(prev => [...prev, {
      id: "demo-3c",
      role: "assistant",
      content: "Refactored the deployment handler to use async/await:\n\n```diff\n--- services/orchestrator/app/agents/devops/deployer.py\n+++ services/orchestrator/app/agents/devops/deployer.py\n@@ -12,15 +12,18 @@\n import boto3\n+import asyncio\n from botocore.exceptions import ClientError\n \n-def deploy_infrastructure(config: dict) -> dict:\n+async def deploy_infrastructure(config: dict) -> dict:\n     \"\"\"Deploy infrastructure to AWS.\"\"\"\n-    client = boto3.client('cloudformation')\n+    session = boto3.Session()\n+    client = session.client('cloudformation')\n     \n     try:\n-        response = client.create_stack(\n+        loop = asyncio.get_event_loop()\n+        response = await loop.run_in_executor(None, lambda: client.create_stack(\n             StackName=config['stack_name'],\n             TemplateBody=config['template'],\n-        )\n+        ))\n         return {'status': 'success', 'stack_id': response['StackId']}\n     except ClientError as e:\n-        return {'status': 'error', 'message': str(e)}\n+        logger.error(f\"Deployment failed: {e}\")\n+        raise DeploymentError(f\"Failed to create stack: {e}\") from e\n```",
      timestamp: new Date(),
      type: "normal",
    }]);

    // Step 9: Add resource comparison table
    await new Promise(resolve => setTimeout(resolve, 1000));
    setMessages(prev => [...prev, {
      id: "demo-4",
      role: "assistant",
      content: "Here's a comparison of the AWS services I'll use:\n\n| Service | Purpose | Estimated Cost | Scalability |\n|---------|---------|----------------|-------------|\n| CloudFront | CDN for static assets | ~$10/month | Auto-scales |\n| API Gateway | REST API endpoint | ~$3.50/1M requests | Auto-scales |\n| Lambda | Serverless compute | ~$0.20/1M requests | Auto-scales |\n| DynamoDB | NoSQL database | ~$1.25/GB + $1.25/1M writes | Auto-scales |\n| Cognito | User authentication | Free up to 50K users | Managed |\n| S3 | File storage | ~$0.023/GB | Unlimited |",
      timestamp: new Date(),
      type: "normal",
    }]);

    // Step 10: Clarification
    await new Promise(resolve => setTimeout(resolve, 1500));
    setMessages(prev => [...prev, {
      id: "demo-5",
      role: "assistant",
      content: "I need to clarify your infrastructure requirements:",
      timestamp: new Date(),
      type: "clarification",
      metadata: {
        clarification: {
          question: "What's your expected monthly traffic volume?",
          context: "This will help me determine the optimal Lambda concurrency and DynamoDB capacity settings.",
          options: ["< 100K requests/month", "100K - 1M requests/month", "> 1M requests/month"],
        },
      },
    }]);
  };

  // Handle state changes from context
  useEffect(() => {
    if (state.needsClarification && state.clarification) {
      const clarificationMsg: Message = {
        id: `clarification-${Date.now()}`,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        type: "clarification",
        metadata: {
          clarification: state.clarification,
          phase: state.currentPhase,
        },
      };
      setMessages(prev => [...prev, clarificationMsg]);
    }
  }, [state.needsClarification, state.clarification]);

  useEffect(() => {
    if (state.needsApproval && state.checkpoint) {
      const checkpointMsg: Message = {
        id: `checkpoint-${Date.now()}`,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        type: "checkpoint",
        metadata: {
          checkpoint: state.checkpoint,
          sectionStates: state.sectionStates,
          phase: state.currentPhase,
        },
      };
      setMessages(prev => [...prev, checkpointMsg]);
    }
  }, [state.needsApproval, state.checkpoint]);

  useEffect(() => {
    if (state.error) {
      const errorMsg: Message = {
        id: `error-${Date.now()}`,
        role: "assistant",
        content: state.error,
        timestamp: new Date(),
        type: "error",
      };
      setMessages(prev => [...prev, errorMsg]);
    }
  }, [state.error]);

  const handleSend = async (quickResponse?: string) => {
    const messageContent = quickResponse || input.trim();
    if (!messageContent || state.isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: messageContent,
      timestamp: new Date(),
      type: "normal",
    };

    setMessages(prev => [...prev, userMessage]);
    setInput("");

    // If we're in clarification or approval mode, send the message as resume_value too
    const resumeValue = (state.needsClarification || state.needsApproval) ? messageContent : quickResponse;
    await sendMessage(messageContent, resumeValue);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleCopyMessage = (content: string) => {
    navigator.clipboard.writeText(content);
  };

  const handleQuickResponse = (response: string) => {
    handleSend(response);
  };

  // Auto-grow textarea
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    const maxHeight = typeof window !== "undefined" ? window.innerHeight * 0.5 : 400;
    el.style.height = "auto";
    const next = Math.min(el.scrollHeight, maxHeight);
    el.style.height = `${next}px`;
    el.style.overflowY = el.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [input]);

  const renderMessage = (message: Message) => {
    if (message.type === "action") {
      return renderActionMessage(message);
    }
    if (message.type === "clarification" && message.metadata?.clarification) {
      return renderClarificationCard(message.metadata.clarification);
    }
    if (message.type === "checkpoint" && message.metadata?.checkpoint) {
      return renderCheckpointCard(message.metadata.checkpoint);
    }
    if (message.type === "error") {
      return renderErrorCard(message.content);
    }
    return renderNormalMessage(message);
  };

  const renderActionMessage = (message: Message) => (
    <ActionMessage
      text={message.metadata?.actionText || ""}
      duration={message.metadata?.actionDuration || ""}
    />
  );

  const renderClarificationCard = (clarification: ClarificationInfo) => (
    <ClarificationCard
      clarification={clarification}
      onResponse={handleQuickResponse}
    />
  );

  const renderCheckpointCard = (checkpoint: CheckpointInfo) => (
    <div className="text-[13px] text-[var(--text-tertiary)] leading-relaxed">
      <p>{checkpoint.message}</p>
    </div>
  );

  // Get human-readable label for current phase
  const getPhaseLabel = (phase: string) => {
    const labels: Record<string, string> = {
      welcome: "welcome",
      clarify: "requirements",
      graph: "services",
      api: "API & roles",
      database: "database",
      constraints: "rules & risks",
      complete: "complete",
    };
    return labels[phase] || phase;
  };

  const renderErrorCard = (content: string) => (
    <div className="rounded-xl border border-[var(--border-color)] bg-[var(--bg-secondary)] p-4 max-w-[90%]">
      <p className="text-xs text-[var(--text-secondary)]">{content}</p>
    </div>
  );

  const renderNormalMessage = (message: Message) => (
    <div
      className={cn(
        "transition-colors",
        message.role === "user"
          ? "rounded-xl px-3 py-2 bg-[var(--bg-tertiary)] text-[var(--text-tertiary)]"
          : "text-[var(--text-tertiary)]" // No bubble for AI messages
      )}
    >
      <div className="text-[13px] leading-relaxed prose max-w-none">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ ...props }) => (
              <h1 className="text-[15px] font-bold mt-3 mb-1.5 text-[var(--text-tertiary)]" {...props} />
            ),
            h2: ({ ...props }) => (
              <h2 className="text-[14px] font-semibold mt-2 mb-1 text-[var(--text-tertiary)]" {...props} />
            ),
            ul: ({ ...props }) => (
              <ul className="list-disc pl-5 my-1.5 space-y-0.5" {...props} />
            ),
            li: ({ ...props }) => (
              <li className="text-[13px]" {...props} />
            ),
            p: ({ ...props }) => (
              <div className="my-1 text-[13px]" {...props} />
            ),
            strong: ({ ...props }) => (
              <strong className="font-semibold text-[var(--text-tertiary)]" {...props} />
            ),
            em: ({ ...props }) => (
              <em className="text-[var(--text-secondary)]" {...props} />
            ),
            code: ({ node, inline, className, children, ...props }: any) => {
              const match = /language-(\w+)/.exec(className || '');
              const language = match ? match[1] : 'code';
              const code = String(children).replace(/\n$/, '');

              if (inline) {
                return (
                  <code className="px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-primary)] text-[10px] font-mono" {...props}>
                    {children}
                  </code>
                );
              }

              // Check if it's a diff
              const isDiff = language === 'diff' || code.includes('\n+') || code.includes('\n-') || code.startsWith('---') || code.startsWith('+++');

              // Render diff with DiffBlock component
              if (isDiff) {
                return <DiffBlock code={code} onCopy={handleCopyMessage} />;
              }

              // Render regular code block with CodeBlock component
              return <CodeBlock code={code} language={language} onCopy={handleCopyMessage} />;
            },
            table: ({ ...props }) => (
              <div className="my-3 overflow-x-auto">
                <table className="min-w-full border-collapse border border-[var(--border-color)]" {...props} />
              </div>
            ),
            thead: ({ ...props }) => (
              <thead className="bg-[var(--bg-tertiary)]" {...props} />
            ),
            tbody: ({ ...props }) => (
              <tbody {...props} />
            ),
            tr: ({ ...props }) => (
              <tr className="border-b border-[var(--border-color)]" {...props} />
            ),
            th: ({ ...props }) => (
              <th className="px-3 py-2 text-left text-[11px] font-semibold text-[var(--text-primary)] border-r border-[var(--border-color)] last:border-r-0" {...props} />
            ),
            td: ({ ...props }) => (
              <td className="px-3 py-2 text-[11px] text-[var(--text-secondary)] border-r border-[var(--border-color)] last:border-r-0" {...props} />
            ),
          }}
        >
          {message.content}
        </ReactMarkdown>
      </div>
    </div>
  );

  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)] transition-colors">
      <ScrollArea className="flex-1 px-4 py-4">
        <div className="space-y-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={cn(
                "flex",
                message.role === "user" ? "justify-end" : "justify-start"
              )}
            >
              <div className={cn(
                "flex flex-col gap-1",
                message.role === "user" ? "items-end max-w-[80%]" : "items-start w-full"
              )}>
                {renderMessage(message)}

                {/* Demo button for welcome message */}
                {message.id === "welcome" && !demoMode && (
                  <button
                    onClick={startDemoFlow}
                    className="mt-3 px-4 py-2 rounded-lg bg-primary hover:bg-primary-hover text-primary-foreground text-[13px] font-medium transition-colors"
                  >
                    See Demo Flow
                  </button>
                )}

                {/* Action buttons for normal assistant messages */}
                {message.role === "assistant" && message.type === "normal" && message.id !== "welcome" && !demoMode && (
                  <div className="flex items-center gap-0.5 mt-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0 hover:bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-tertiary)]"
                      onClick={() => handleCopyMessage(message.content)}
                      title="Copy"
                    >
                      <Copy className="h-3 w-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0 hover:bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-tertiary)]"
                      title="Regenerate"
                    >
                      <RotateCw className="h-3 w-3" />
                    </Button>
                    <Button variant="ghost" size="sm" className="h-6 w-6 p-0 hover:bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-tertiary)]" title="Good response">
                      <ThumbsUp className="h-3 w-3" />
                    </Button>
                    <Button variant="ghost" size="sm" className="h-6 w-6 p-0 hover:bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-tertiary)]" title="Bad response">
                      <ThumbsDown className="h-3 w-3" />
                    </Button>
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Thinking state */}
          {showThinking && (
            <div className="flex justify-start">
              <div className="flex items-center gap-2 text-[var(--text-secondary)]">
                <span className="text-[13px] shimmer-text">
                  Thinking
                </span>
              </div>
            </div>
          )}

          {/* Action messages */}
          {actionMessages.length > 0 && (
            <div className="flex justify-start">
              <div className="flex flex-col gap-0.5 items-start">
                {actionMessages.map((action, idx) => (
                  <div key={idx} className="text-[11px] text-[var(--text-secondary)]">
                    {action}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Streaming text */}
          {isStreaming && streamingText && (
            <div className="flex justify-start">
              <div className="flex flex-col gap-1 items-start w-full">
                <div className="text-[var(--text-secondary)] opacity-60">
                  <div className="text-[13px] leading-relaxed">
                    {streamingText}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Loading state */}
          {state.isLoading && !isStreaming && !showThinking && (
            <div className="flex justify-start">
              <div className="flex items-center gap-2 text-[var(--text-secondary)]">
                <span className="text-[13px] shimmer-text">
                  Designing architecture
                </span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Approve Bar - above input, hidden during loading */}
      {state.needsApproval && state.checkpoint && !state.isLoading && (
        <div className="border-t border-[var(--border-color)] bg-[var(--bg-secondary)] px-4 py-2">
          <div className="flex items-center justify-between">
            <span className="text-[13px] text-[var(--text-secondary)]">
              Review: <span className="text-[var(--text-tertiary)] font-medium">{getPhaseLabel(state.checkpoint.section_name)}</span>
            </span>
            <button
              onClick={() => handleQuickResponse("Approve")}
              className="px-3 py-1 rounded-md bg-[var(--text-tertiary)] text-[var(--bg-primary)] text-[12px] font-medium transition-colors hover:opacity-90"
            >
              Approve
            </button>
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="border-t border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-3 transition-colors">
        <div className="border border-[var(--border-color)] rounded-xl bg-[var(--bg-primary)] px-3 py-2 transition-colors">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyPress}
            placeholder={
              state.needsClarification
                ? "Type your answer..."
                : state.needsApproval
                ? "Type feedback or click Approve..."
                : "Describe your application..."
            }
            disabled={state.isLoading}
            className="min-h-[24px] w-full resize-none border-none bg-transparent px-0 py-0 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] shadow-none focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:outline-none"
          />

          <div className="flex items-center justify-end gap-1 pt-1">
            <Button variant="ghost" size="sm" className="h-7 w-7 p-0 hover:bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-tertiary)] rounded-md" title="Attach file">
              <Paperclip className="h-3.5 w-3.5" />
            </Button>
            <Button
              onClick={() => handleSend()}
              disabled={state.isLoading || !input.trim()}
              size="sm"
              className="h-7 w-7 p-0 bg-neutral-800 dark:bg-neutral-200 hover:bg-neutral-900 dark:hover:bg-neutral-100 hover:scale-105 active:scale-95 text-white dark:text-black rounded-md disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:scale-100 transition-all duration-150"
              title="Send message"
            >
              <Send className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
