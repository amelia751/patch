"use client";

import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { HeartPulse, ScrollText, History } from "lucide-react";
import { HealthTab } from "@/components/interface/monitor/health-tab";
import { LogsTab } from "@/components/interface/monitor/logs-tab";
import { HistoryTab } from "@/components/interface/monitor/history-tab";

// ============================================================================
// MOCK DATA — Health
// ============================================================================

const MOCK_ENVIRONMENTS = {
  dev: {
    status: "healthy" as const,
    services_count: 4,
    alerts_count: 1,
    endpoint_url: "https://dev-api.ecommerce-a3f2k.patchapi.dev",
    last_deployed: "2026-01-10T08:20:00Z",
    monthly_cost: 47.80,
    services: [
      { name: "auth-service", type: "lambda", status: "healthy" as const, requests_24h: 1250, errors_24h: 3, avg_duration_ms: 45, memory_mb: 256 },
      { name: "product-service", type: "lambda", status: "healthy" as const, requests_24h: 3420, errors_24h: 0, avg_duration_ms: 32, memory_mb: 512 },
      { name: "order-service", type: "lambda", status: "warning" as const, requests_24h: 890, errors_24h: 12, avg_duration_ms: 156, memory_mb: 512 },
      { name: "payment-service", type: "lambda", status: "healthy" as const, requests_24h: 445, errors_24h: 1, avg_duration_ms: 234, memory_mb: 256 },
    ],
    databases: [
      { name: "main-db", type: "aurora-postgresql", status: "healthy" as const, connections: 12, max_connections: 100, storage_gb: 5.2, cpu_percent: 15 },
    ],
    storage: [
      { name: "uploads-bucket", type: "s3", objects: 1523, size_gb: 2.4 },
      { name: "assets-bucket", type: "s3", objects: 89, size_gb: 0.3 },
    ],
  },
  staging: {
    status: "degraded" as const,
    services_count: 3,
    alerts_count: 2,
    endpoint_url: "https://staging-api.ecommerce-a3f2k.patchapi.dev",
    last_deployed: "2026-01-08T14:40:00Z",
    monthly_cost: 89.50,
    services: [
      { name: "auth-service", type: "lambda", status: "healthy" as const, requests_24h: 450, errors_24h: 0, avg_duration_ms: 42, memory_mb: 512 },
      { name: "product-service", type: "lambda", status: "healthy" as const, requests_24h: 1200, errors_24h: 2, avg_duration_ms: 28, memory_mb: 1024 },
      { name: "order-service", type: "lambda", status: "error" as const, requests_24h: 320, errors_24h: 45, avg_duration_ms: 890, memory_mb: 1024 },
    ],
    databases: [
      { name: "main-db", type: "aurora-postgresql", status: "healthy" as const, connections: 8, max_connections: 100, storage_gb: 3.1, cpu_percent: 8 },
    ],
    storage: [],
  },
  prod: {
    status: "not_deployed" as const,
    services_count: 0,
    alerts_count: 0,
  },
};

const MOCK_INSIGHTS = [
  {
    id: "insight-1",
    severity: "critical" as const,
    service: "order-service",
    environment: "staging",
    title: "Error rate at 14% — DynamoDB throttling",
    ai_diagnosis: "The order-service is experiencing DynamoDB read throttling. Burst capacity was exhausted after the product catalog import job at 09:30 UTC. The table provisioned throughput is set to 5 RCU, but the import triggered 80+ RCU sustained reads. This is causing the order validation step to fail with ProvisionedThroughputExceededException.",
    suggested_action: "Remediate",
    timestamp: "2026-01-10T09:45:00Z",
  },
  {
    id: "insight-2",
    severity: "warning" as const,
    service: "order-service",
    environment: "staging",
    title: "Latency spike — avg response 890ms",
    ai_diagnosis: "Average response time increased from 156ms to 890ms in the last 2 hours. This correlates with the DynamoDB throttling above — failed reads trigger 3 retries with exponential backoff before returning an error, inflating the overall latency.",
    suggested_action: "View Logs",
    timestamp: "2026-01-10T10:00:00Z",
  },
  {
    id: "insight-3",
    severity: "warning" as const,
    service: "order-service",
    environment: "dev",
    title: "12 errors in 24h — null pointer in validation",
    ai_diagnosis: "All 12 errors trace to OrderValidator.validate() throwing a NullPointerException when the cart items array is empty. This is an edge case in the validation logic — the handler doesn't check for empty cart before accessing items[0]. Non-critical but worth fixing.",
    suggested_action: "View Logs",
    timestamp: "2026-01-10T10:15:00Z",
  },
  {
    id: "insight-4",
    severity: "info" as const,
    service: "auth-service",
    environment: "dev",
    title: "Token refresh rate increased 3x",
    ai_diagnosis: "Token refresh requests increased from ~100/day to ~300/day. This is likely due to shorter token TTL configured last week (30min → 10min). Not an issue — just higher call volume. Monitor if it impacts Cognito costs.",
    suggested_action: "Dismiss",
    timestamp: "2026-01-10T08:30:00Z",
  },
];

// ============================================================================
// MOCK DATA — Service Logs
// ============================================================================

const MOCK_SERVICES = ["auth-service", "product-service", "order-service", "payment-service"];

const MOCK_LOGS = [
  { id: "log-001", timestamp: "2026-01-10T10:30:15Z", service: "auth-service", level: "info" as const, message: "User login successful: user_123 (email: john@example.com)", trace_id: "tr-a1b2c3" },
  { id: "log-002", timestamp: "2026-01-10T10:30:14Z", service: "auth-service", level: "debug" as const, message: "Token generated: TTL=600s, scopes=[read, write]", trace_id: "tr-a1b2c3" },
  { id: "log-003", timestamp: "2026-01-10T10:30:12Z", service: "product-service", level: "info" as const, message: "GET /api/products — 25 results, 32ms", trace_id: "tr-d4e5f6" },
  { id: "log-004", timestamp: "2026-01-10T10:30:10Z", service: "order-service", level: "warn" as const, message: "Slow DynamoDB read: GetItem took 245ms (threshold: 100ms)", trace_id: "tr-g7h8i9" },
  { id: "log-005", timestamp: "2026-01-10T10:30:08Z", service: "order-service", level: "error" as const, message: "ProvisionedThroughputExceededException: Cannot read from orders table — insufficient read capacity", trace_id: "tr-j0k1l2" },
  { id: "log-006", timestamp: "2026-01-10T10:30:05Z", service: "order-service", level: "error" as const, message: "OrderValidator.validate() — NullPointerException: Cannot read property 'price' of undefined at items[0]", trace_id: "tr-m3n4o5" },
  { id: "log-007", timestamp: "2026-01-10T10:29:58Z", service: "auth-service", level: "info" as const, message: "Token refresh for user_456 — new TTL=600s", trace_id: "tr-p6q7r8" },
  { id: "log-008", timestamp: "2026-01-10T10:29:55Z", service: "payment-service", level: "info" as const, message: "Payment intent created: pi_3Ox1abc — amount=$49.99 currency=usd", trace_id: "tr-s9t0u1" },
  { id: "log-009", timestamp: "2026-01-10T10:29:50Z", service: "product-service", level: "debug" as const, message: "Cache hit for product_list — returning 25 items from Redis", trace_id: "tr-v2w3x4" },
  { id: "log-010", timestamp: "2026-01-10T10:29:45Z", service: "order-service", level: "warn" as const, message: "Retry attempt 2/3 for DynamoDB GetItem on orders table", trace_id: "tr-j0k1l2" },
  { id: "log-011", timestamp: "2026-01-10T10:29:40Z", service: "auth-service", level: "info" as const, message: "New user registration: user_789 (email: sarah@example.com)", trace_id: "tr-y5z6a7" },
  { id: "log-012", timestamp: "2026-01-10T10:29:35Z", service: "product-service", level: "info" as const, message: "GET /api/products/search?q=laptop — 8 results, 45ms", trace_id: "tr-b8c9d0" },
  { id: "log-013", timestamp: "2026-01-10T10:29:30Z", service: "order-service", level: "error" as const, message: "Failed to process order ord_12345: DynamoDB throughput exceeded after 3 retries", trace_id: "tr-j0k1l2" },
  { id: "log-014", timestamp: "2026-01-10T10:29:25Z", service: "payment-service", level: "info" as const, message: "Payment confirmed: pi_3Ox1abc — status=succeeded", trace_id: "tr-s9t0u1" },
  { id: "log-015", timestamp: "2026-01-10T10:29:20Z", service: "auth-service", level: "info" as const, message: "Password reset requested for email: mike@example.com", trace_id: "tr-e1f2g3" },
  { id: "log-016", timestamp: "2026-01-10T10:29:15Z", service: "product-service", level: "info" as const, message: "POST /api/products/reviews — review submitted for product_42", trace_id: "tr-h4i5j6" },
  { id: "log-017", timestamp: "2026-01-10T10:29:10Z", service: "order-service", level: "info" as const, message: "Order ord_12340 created successfully: 3 items, total=$127.50", trace_id: "tr-k7l8m9" },
  { id: "log-018", timestamp: "2026-01-10T10:29:05Z", service: "auth-service", level: "warn" as const, message: "Rate limit approaching for IP 192.168.1.100 — 45/50 requests in 60s window", trace_id: "tr-n0o1p2" },
  { id: "log-019", timestamp: "2026-01-10T10:29:00Z", service: "product-service", level: "debug" as const, message: "Cache miss for product_42 — fetching from DynamoDB", trace_id: "tr-q3r4s5" },
  { id: "log-020", timestamp: "2026-01-10T10:28:55Z", service: "payment-service", level: "warn" as const, message: "Stripe webhook received: invoice.payment_failed for customer cus_abc123", trace_id: "tr-t6u7v8" },
  { id: "log-021", timestamp: "2026-01-10T10:28:50Z", service: "order-service", level: "info" as const, message: "Order status updated: ord_12338 → shipped", trace_id: "tr-w9x0y1" },
  { id: "log-022", timestamp: "2026-01-10T10:28:45Z", service: "auth-service", level: "info" as const, message: "Session extended for user_123 — new expiry in 30min", trace_id: "tr-z2a3b4" },
  { id: "log-023", timestamp: "2026-01-10T10:28:40Z", service: "product-service", level: "info" as const, message: "Inventory check: product_42 — 15 units remaining", trace_id: "tr-c5d6e7" },
  { id: "log-024", timestamp: "2026-01-10T10:28:35Z", service: "order-service", level: "error" as const, message: "OrderValidator.validate() — NullPointerException: cart items array is empty", trace_id: "tr-f8g9h0" },
  { id: "log-025", timestamp: "2026-01-10T10:28:30Z", service: "payment-service", level: "info" as const, message: "Refund processed: re_abc123 — amount=$29.99 → customer cus_xyz", trace_id: "tr-i1j2k3" },
];

// ============================================================================
// MOCK DATA — History
// ============================================================================

const MOCK_DEPLOYMENTS = [
  {
    id: "deploy-001",
    environment: "dev",
    status: "success" as const,
    deployed_at: "2026-01-10T08:20:00Z",
    deployed_by: "john@example.com",
    duration_seconds: 245,
    version: "v3",
    changes: { created: 2, updated: 1, deleted: 0 },
    cost_delta: "+$8.50/month",
  },
  {
    id: "deploy-002",
    environment: "staging",
    status: "success" as const,
    deployed_at: "2026-01-08T14:40:00Z",
    deployed_by: "sarah@example.com",
    duration_seconds: 287,
    version: "v2",
    changes: { created: 0, updated: 3, deleted: 0 },
    approved_by: "sarah@example.com",
  },
  {
    id: "deploy-003",
    environment: "dev",
    status: "success" as const,
    deployed_at: "2026-01-08T14:35:00Z",
    deployed_by: "john@example.com",
    duration_seconds: 198,
    version: "v2",
    changes: { created: 0, updated: 3, deleted: 0 },
  },
  {
    id: "deploy-004",
    environment: "dev",
    status: "failed" as const,
    deployed_at: "2026-01-05T16:45:00Z",
    deployed_by: "john@example.com",
    duration_seconds: 145,
    version: "v1",
    error: "Failed to create RDS instance: InsufficientDBInstanceCapacity — requested db.t3.medium is not available in us-east-1a. Remediation: use us-east-1b or db.t3.small.",
  },
  {
    id: "deploy-005",
    environment: "dev",
    status: "success" as const,
    deployed_at: "2026-01-05T10:20:00Z",
    deployed_by: "john@example.com",
    duration_seconds: 425,
    version: "v1",
    changes: { created: 12, updated: 0, deleted: 0 },
    initial_deployment: true,
  },
];

const MOCK_DRIFT_EVENTS = [
  {
    id: "drift-001",
    detected_at: "2026-01-09T15:30:00Z",
    resource: "order-service",
    resource_type: "Lambda",
    drift_type: "config_change" as const,
    detail: "Memory configuration changed externally: 512MB → 1024MB. This was modified directly in the AWS console, bypassing PatchAPI.",
    severity: "medium" as const,
    auto_reconciled: true,
    reconciled_at: "2026-01-09T15:35:00Z",
  },
  {
    id: "drift-002",
    detected_at: "2026-01-09T12:00:00Z",
    resource: "staging-cache",
    resource_type: "ElastiCache",
    drift_type: "orphaned" as const,
    detail: "ElastiCache cluster 'ecommerce-staging-cache' found in AWS but not tracked by PatchAPI. This may be a manually created resource or leftover from a failed deployment.",
    severity: "low" as const,
    auto_reconciled: false,
  },
  {
    id: "drift-003",
    detected_at: "2026-01-07T09:15:00Z",
    resource: "uploads-bucket",
    resource_type: "S3",
    drift_type: "config_change" as const,
    detail: "Bucket versioning was disabled externally. PatchAPI expects versioning=enabled per architecture spec.",
    severity: "high" as const,
    auto_reconciled: true,
    reconciled_at: "2026-01-07T09:20:00Z",
  },
];

// ============================================================================
// PAGE COMPONENT
// ============================================================================

export default function MonitorPage() {
  const [currentEnvironment, setCurrentEnvironment] = useState("dev");

  // Count alerts for badge
  const totalInsights = MOCK_INSIGHTS.filter((i) => i.severity === "critical" || i.severity === "warning").length;
  const unresolvedDrift = MOCK_DRIFT_EVENTS.filter((d) => !d.auto_reconciled).length;

  return (
    <div className="h-full flex flex-col">
      <Tabs defaultValue="health" className="h-full flex flex-col">
        {/* Header */}
        <div className="border-b border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-2 transition-colors">
          <div className="flex items-center justify-between mb-2">
            <h1 className="text-base font-semibold text-[var(--text-primary)]">Monitor</h1>
          </div>

          <TabsList className="inline-flex w-full h-9 items-center justify-between rounded-lg bg-[var(--bg-secondary)] p-1 text-[var(--text-secondary)] transition-colors">
            <TabsTrigger
              value="health"
              className="flex-1 inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-[11px] font-medium transition-all data-[state=active]:bg-[var(--bg-primary)] data-[state=active]:text-[var(--text-tertiary)] data-[state=active]:shadow relative"
            >
              <HeartPulse className="w-3 h-3 mr-2" />
              Health
              {totalInsights > 0 && (
                <span className="ml-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 text-[9px] text-white font-bold px-1">
                  {totalInsights}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger
              value="logs"
              className="flex-1 inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-[11px] font-medium transition-all data-[state=active]:bg-[var(--bg-primary)] data-[state=active]:text-[var(--text-tertiary)] data-[state=active]:shadow"
            >
              <ScrollText className="w-3 h-3 mr-2" />
              Logs
            </TabsTrigger>
            <TabsTrigger
              value="history"
              className="flex-1 inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-[11px] font-medium transition-all data-[state=active]:bg-[var(--bg-primary)] data-[state=active]:text-[var(--text-tertiary)] data-[state=active]:shadow relative"
            >
              <History className="w-3 h-3 mr-2" />
              History
              {unresolvedDrift > 0 && (
                <span className="ml-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 text-[9px] text-white font-bold px-1">
                  {unresolvedDrift}
                </span>
              )}
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="health" className="flex-1 m-0 p-0 overflow-hidden">
          <HealthTab
            environments={MOCK_ENVIRONMENTS}
            insights={MOCK_INSIGHTS}
            currentEnvironment={currentEnvironment}
            onEnvironmentChange={setCurrentEnvironment}
          />
        </TabsContent>

        <TabsContent value="logs" className="flex-1 m-0 p-0 overflow-hidden relative">
          <LogsTab logs={MOCK_LOGS} services={MOCK_SERVICES} />
        </TabsContent>

        <TabsContent value="history" className="flex-1 m-0 p-0 overflow-hidden">
          <HistoryTab deployments={MOCK_DEPLOYMENTS} driftEvents={MOCK_DRIFT_EVENTS} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
