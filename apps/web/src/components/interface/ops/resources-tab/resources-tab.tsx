"use client";

import { useState, useMemo, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { NoProjectEmptyState } from "./no-project-empty-state";
import { ResourcesEmptyState } from "../empty-states";
import {
  Server,
  Database,
  HardDrive,
  Network,
  Shield,
  ChevronRight,
  ChevronDown,
  HandCoins,
  Search,
  Filter,
  Clock,
  MapPin,
  ExternalLink,
  Trash2,
  // Temporarily hidden - test feature
  // SquareDashedMousePointer,
  AlertCircle,
  CheckCircle2,
  Loader2,
  Box,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getGCPServiceIcon, getGCPCategoryIcon } from "@/lib/gcp-icons";
import Image from "next/image";

const AWS_ICON = "/aws-dark.svg";

function getServiceIcon(resourceType: string, cloudProvider?: string): string {
  if (cloudProvider === "aws") {
    return AWS_ICON;
  }
  return getGCPServiceIcon(resourceType);
}
// Temporarily hidden - test feature
// import { TestResourceDialog } from "./test-resource-dialog";

type ResourceStatus = "active" | "updating" | "failed" | "deleted" | "pending";

// GCP categories (5 simple categories)
type GCPResourceType = "compute" | "database" | "storage" | "networking" | "security";

// AWS categories (25 detailed categories)
type AWSResourceType =
  | "analytics"
  | "app-integration"
  | "artificial-intelligence"
  | "blockchain"
  | "business-applications"
  | "cloud-financial-management"
  | "compute"
  | "contact-center"
  | "containers"
  | "customer-enablement"
  | "database"
  | "developer-tools"
  | "end-user-computing"
  | "front-end-web-mobile"
  | "games"
  | "internet-of-things"
  | "management-governance"
  | "media-services"
  | "migration-modernization"
  | "networking-content-delivery"
  | "quantum-technologies"
  | "satellite"
  | "security-identity-compliance"
  | "serverless"
  | "storage";

// Combined type for all categories
type ResourceType = GCPResourceType | AWSResourceType;

interface DeployedResource {
  id: string;
  name: string;
  type: string;
  category: ResourceType;
  status: ResourceStatus;
  region: string;
  cost?: number;
  created_at: string;
  updated_at: string;
  version: string;
  dependencies: string[];
  arn?: string;
  cloud_id?: string;
  cloud_arn?: string;
  cloud_provider?: string;
  metadata: Record<string, unknown>;
}

interface DeployTabProps {
  pendingChanges?: any;
  approvalWorkflow?: any;
  hasProject?: boolean;
  projectId?: string; // For fetching real resources
  mockResources?: DeployedResource[]; // Mock resources for demo mode
  cloudProvider?: string; // Cloud provider (aws or gcp)
}

// Mock GCP deployed resources
const MOCK_DEPLOYED_RESOURCES: DeployedResource[] = [
  // Compute
  {
    id: "cr-1",
    name: "auth-service",
    type: "Cloud Run",
    category: "compute",
    status: "active",
    region: "us-central1",
    cost: 45.20,
    created_at: "2024-01-05T10:00:00Z",
    updated_at: "2024-02-04T15:30:00Z",
    version: "v3",
    dependencies: ["firestore-users", "secret-jwt-key"],
    arn: "projects/my-project/locations/us-central1/services/auth-service",
    metadata: { cpu: "1000m", memory: "512Mi", min_instances: 1 },
  },
  {
    id: "cr-2",
    name: "payment-service",
    type: "Cloud Run",
    category: "compute",
    status: "updating",
    region: "us-central1",
    cost: 58.00,
    created_at: "2024-01-08T14:20:00Z",
    updated_at: "2024-02-05T16:45:00Z",
    version: "v5",
    dependencies: ["firestore-transactions", "stripe-secret"],
    arn: "projects/my-project/locations/us-central1/services/payment-service",
    metadata: { cpu: "2000m", memory: "1Gi", min_instances: 2 },
  },
  {
    id: "cf-1",
    name: "image-processor",
    type: "Cloud Functions",
    category: "compute",
    status: "active",
    region: "us-east1",
    cost: 12.50,
    created_at: "2024-01-15T09:00:00Z",
    updated_at: "2024-01-20T11:15:00Z",
    version: "v1",
    dependencies: ["storage-images"],
    arn: "projects/my-project/locations/us-east1/functions/image-processor",
    metadata: { runtime: "python311", trigger: "storage" },
  },
  {
    id: "cr-3",
    name: "notification-service",
    type: "Cloud Run",
    category: "compute",
    status: "active",
    region: "us-central1",
    cost: 22.80,
    created_at: "2024-01-22T13:30:00Z",
    updated_at: "2024-02-01T09:20:00Z",
    version: "v2",
    dependencies: ["pubsub-notifications"],
    arn: "projects/my-project/locations/us-central1/services/notification-service",
    metadata: { cpu: "500m", memory: "256Mi", min_instances: 0 },
  },
  // Database
  {
    id: "fs-1",
    name: "firestore-users",
    type: "Firestore",
    category: "database",
    status: "active",
    region: "us-central1",
    cost: 85.40,
    created_at: "2024-01-05T10:00:00Z",
    updated_at: "2024-02-03T14:25:00Z",
    version: "v1",
    dependencies: [],
    arn: "projects/my-project/databases/firestore-users",
    metadata: { mode: "native", location: "us-central1" },
  },
  {
    id: "fs-2",
    name: "firestore-transactions",
    type: "Firestore",
    category: "database",
    status: "active",
    region: "us-central1",
    cost: 125.60,
    created_at: "2024-01-08T14:20:00Z",
    updated_at: "2024-02-05T10:15:00Z",
    version: "v2",
    dependencies: [],
    arn: "projects/my-project/databases/firestore-transactions",
    metadata: { mode: "native", location: "us-central1" },
  },
  {
    id: "sql-1",
    name: "analytics-db",
    type: "Cloud SQL",
    category: "database",
    status: "failed",
    region: "us-east1",
    cost: 220.00,
    created_at: "2024-01-18T11:00:00Z",
    updated_at: "2024-02-05T08:30:00Z",
    version: "v1",
    dependencies: [],
    arn: "projects/my-project/instances/analytics-db",
    metadata: { tier: "db-n1-standard-2", version: "POSTGRES_14" },
  },
  // Storage
  {
    id: "gcs-1",
    name: "storage-images",
    type: "Cloud Storage",
    category: "storage",
    status: "active",
    region: "us-central1",
    cost: 42.30,
    created_at: "2024-01-05T10:00:00Z",
    updated_at: "2024-02-04T16:00:00Z",
    version: "v1",
    dependencies: [],
    arn: "projects/my-project/buckets/storage-images",
    metadata: { storage_class: "STANDARD", size_gb: 1250 },
  },
  {
    id: "gcs-2",
    name: "backup-bucket",
    type: "Cloud Storage",
    category: "storage",
    status: "active",
    region: "us-east1",
    cost: 18.90,
    created_at: "2024-01-12T09:30:00Z",
    updated_at: "2024-01-28T12:45:00Z",
    version: "v1",
    dependencies: [],
    arn: "projects/my-project/buckets/backup-bucket",
    metadata: { storage_class: "NEARLINE", size_gb: 850 },
  },
  // Networking
  {
    id: "lb-1",
    name: "main-load-balancer",
    type: "Cloud Load Balancing",
    category: "networking",
    status: "active",
    region: "global",
    cost: 35.50,
    created_at: "2024-01-05T10:00:00Z",
    updated_at: "2024-02-02T11:20:00Z",
    version: "v2",
    dependencies: ["auth-service", "payment-service"],
    arn: "projects/my-project/global/loadBalancers/main-lb",
    metadata: { type: "HTTPS", backend_services: 4 },
  },
  {
    id: "vpc-1",
    name: "production-vpc",
    type: "VPC Network",
    category: "networking",
    status: "active",
    region: "global",
    cost: 15.00,
    created_at: "2024-01-05T10:00:00Z",
    updated_at: "2024-01-10T14:00:00Z",
    version: "v1",
    dependencies: [],
    arn: "projects/my-project/global/networks/production-vpc",
    metadata: { subnets: 3, auto_create_subnets: false },
  },
  // Security
  {
    id: "sm-1",
    name: "secret-jwt-key",
    type: "Secret Manager",
    category: "security",
    status: "active",
    region: "global",
    cost: 0.10,
    created_at: "2024-01-05T10:00:00Z",
    updated_at: "2024-01-25T16:30:00Z",
    version: "v2",
    dependencies: [],
    arn: "projects/my-project/secrets/jwt-key",
    metadata: { versions: 2, rotation: "manual" },
  },
  {
    id: "sm-2",
    name: "stripe-secret",
    type: "Secret Manager",
    category: "security",
    status: "active",
    region: "global",
    cost: 0.10,
    created_at: "2024-01-08T14:20:00Z",
    updated_at: "2024-01-08T14:20:00Z",
    version: "v1",
    dependencies: [],
    arn: "projects/my-project/secrets/stripe-key",
    metadata: { versions: 1, rotation: "automatic" },
  },
];

// Fallback lucide icons for categories (used when service icon not found)
const categoryIconsFallback: Partial<Record<ResourceType, React.ReactNode>> = {
  compute: <Server className="h-4 w-4" />,
  database: <Database className="h-4 w-4" />,
  storage: <HardDrive className="h-4 w-4" />,
  networking: <Network className="h-4 w-4" />,
  security: <Shield className="h-4 w-4" />,
  "networking-content-delivery": <Network className="h-4 w-4" />,
  "security-identity-compliance": <Shield className="h-4 w-4" />,
  containers: <Server className="h-4 w-4" />,
};

const categoryLabels: Record<ResourceType, string> = {
  // GCP categories (simple 5-category system)
  compute: "Compute",
  database: "Databases",
  storage: "Storage",
  networking: "Networking",
  security: "Security",

  // AWS-specific categories (detailed 25-category system)
  "analytics": "Analytics",
  "app-integration": "Application Integration",
  "artificial-intelligence": "Artificial Intelligence",
  "blockchain": "Blockchain",
  "business-applications": "Business Applications",
  "cloud-financial-management": "Cloud Financial Management",
  "contact-center": "Contact Center",
  "containers": "Containers",
  "customer-enablement": "Customer Enablement",
  "developer-tools": "Developer Tools",
  "end-user-computing": "End User Computing",
  "front-end-web-mobile": "Front-End Web & Mobile",
  "games": "Games",
  "internet-of-things": "Internet of Things",
  "management-governance": "Management & Governance",
  "media-services": "Media Services",
  "migration-modernization": "Migration & Modernization",
  "networking-content-delivery": "Networking & Content Delivery",
  "quantum-technologies": "Quantum Technologies",
  "satellite": "Satellite",
  "security-identity-compliance": "Security, Identity & Compliance",
  "serverless": "Serverless",
};

const statusConfig: Record<ResourceStatus, { icon: React.ReactNode; color: string; bgColor: string }> = {
  active: {
    icon: <CheckCircle2 className="h-3 w-3" />,
    color: "text-[#10b981]",
    bgColor: "bg-[#10b981]/10 border-[#10b981]/30",
  },
  pending: {
    icon: <Loader2 className="h-3 w-3 animate-spin" />,
    color: "text-blue-500",
    bgColor: "bg-blue-500/10 border-blue-500/30",
  },
  updating: {
    icon: <Loader2 className="h-3 w-3 animate-spin" />,
    color: "text-amber-500",
    bgColor: "bg-amber-500/10 border-amber-500/30",
  },
  failed: {
    icon: <AlertCircle className="h-3 w-3" />,
    color: "text-red-500",
    bgColor: "bg-red-500/10 border-red-500/30",
  },
  deleted: {
    icon: <AlertCircle className="h-3 w-3" />,
    color: "text-[var(--text-secondary)]",
    bgColor: "bg-[var(--bg-tertiary)] border-[var(--border-color)]",
  },
};

export function DeployTab({ hasProject = true, projectId, mockResources, cloudProvider: cloudProviderProp }: DeployTabProps) {
  const [environment, setEnvironment] = useState<string>("dev");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<ResourceStatus | "all">("all");
  const [categoryFilter, setCategoryFilter] = useState<ResourceType | "all">("all");
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(["compute", "database"]));
  const [expandedResources, setExpandedResources] = useState<Set<string>>(new Set());
  // Temporarily hidden - test feature
  // const [testingResource, setTestingResource] = useState<DeployedResource | null>(null);

  // State for real resources
  const [resources, setResources] = useState<DeployedResource[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cloudProviderFromAPI, setCloudProviderFromAPI] = useState<string | null>(null);

  // Use cloud provider from props if available, otherwise from API, otherwise default to gcp
  const cloudProvider = cloudProviderProp || cloudProviderFromAPI || "gcp";

  // Fetch resources from API
  const fetchResources = async () => {
    if (!projectId) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/projects/${projectId}/resources?environment=${environment}`,
        { credentials: "include" }
      );

      // Silently fall back to mock data for auth issues or missing endpoints
      if (response.status === 401 || response.status === 404) {
        setIsLoading(false);
        return;
      }

      if (!response.ok) {
        throw new Error(`Failed to fetch resources: ${response.status}`);
      }

      const data = await response.json();

      // Transform API response to match DeployedResource interface
      const transformedResources: DeployedResource[] = data.resources.map((r: any) => ({
        id: r.id || r.cloud_id,
        name: r.name,
        type: r.type,
        category: r.category as ResourceType,
        status: r.status as ResourceStatus,
        region: r.region,
        cost: 0, // Cost not tracked yet
        created_at: r.created_at,
        updated_at: r.updated_at,
        version: r.version,
        dependencies: r.dependencies || [],
        arn: r.cloud_arn || "",
        cloud_id: r.cloud_id,
        cloud_arn: r.cloud_arn,
        cloud_provider: r.cloud_provider,
        metadata: r.metadata || {},
      }));

      setResources(transformedResources);
      setCloudProviderFromAPI(data.cloud_provider || "gcp");
    } catch (err) {
      console.error("Error fetching resources:", err);
      setError(err instanceof Error ? err.message : "Failed to fetch resources");
      // Use mock data as fallback in demo mode (no projectId)
    } finally {
      setIsLoading(false);
    }
  };

  // Fetch resources on mount and when environment changes
  useEffect(() => {
    if (projectId && !mockResources) {
      fetchResources();
    }
  }, [projectId, environment, mockResources]);

  // Listen for deployment_status SSE events — refresh resources when deploy completes
  useEffect(() => {
    if (mockResources || !projectId) return;

    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const url = `${API_URL}/api/projects/${projectId}/stream`;
    let es: EventSource | null = null;
    let timeoutId: ReturnType<typeof setTimeout>;

    const connect = () => {
      try {
        es = new EventSource(url, { withCredentials: true });
        es.onmessage = (e) => {
          try {
            const event = JSON.parse(e.data);
            if (
              event.type === "deployment_status" &&
              event.metadata?.status === "completed"
            ) {
              fetchResources();
            }
          } catch { /* ignore parse errors */ }
        };
        es.onerror = () => {
          es?.close();
          es = null;
          timeoutId = setTimeout(connect, 30000);
        };
      } catch { /* ignore connection errors */ }
    };

    connect();
    return () => {
      es?.close();
      clearTimeout(timeoutId);
    };
  }, [mockResources, projectId]);

  // Use mock resources (from props) > real resources > fallback mock
  const displayResources = mockResources 
    ? mockResources.map((r: any) => ({
        ...r,
        category: r.category as ResourceType,
        status: (r.status === "deployed" ? "active" : r.status) as ResourceStatus,
        cost: 0,
        arn: r.cloud_arn || r.arn || "",
      }))
    : projectId && resources.length > 0 
      ? resources 
      : MOCK_DEPLOYED_RESOURCES;

  // Filter resources
  const filteredResources = useMemo(() => {
    return displayResources.filter((resource) => {
      const matchesSearch = resource.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                            resource.type.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesStatus = statusFilter === "all" || resource.status === statusFilter;
      const matchesCategory = categoryFilter === "all" || resource.category === categoryFilter;
      return matchesSearch && matchesStatus && matchesCategory;
    });
  }, [displayResources, searchQuery, statusFilter, categoryFilter]);

  // Group resources by category (dynamically based on what categories exist)
  const resourcesByCategory = useMemo(() => {
    const grouped: Record<string, DeployedResource[]> = {};

    filteredResources.forEach((resource) => {
      const category = resource.category as string;
      if (!grouped[category]) {
        grouped[category] = [];
      }
      grouped[category].push(resource);
    });

    // Deduplicate each category — API can return the same resource multiple times
    for (const category of Object.keys(grouped)) {
      const seenIds = new Set<string>();
      grouped[category] = grouped[category].filter((r) => {
        if (seenIds.has(r.id)) return false;
        seenIds.add(r.id);
        return true;
      });
    }

    return grouped;
  }, [filteredResources]);

  const toggleCategory = (category: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  };

  const toggleResource = (resourceId: string) => {
    setExpandedResources((prev) => {
      const next = new Set(prev);
      if (next.has(resourceId)) {
        next.delete(resourceId);
      } else {
        next.add(resourceId);
      }
      return next;
    });
  };

  // No project selected - show empty state
  if (!hasProject) {
    return <NoProjectEmptyState />;
  }

  // Show loading state (but not if we have mockResources)
  if (isLoading && projectId && !mockResources) {
    return (
      <div className="h-full flex flex-col items-center justify-center bg-[var(--bg-primary)] p-8">
        <Loader2 className="h-8 w-8 animate-spin text-[var(--text-secondary)] mb-4" />
        <p className="text-sm text-[var(--text-secondary)]">Loading resources...</p>
      </div>
    );
  }

  // Show error state with retry (but not if we have mockResources)
  if (error && projectId && resources.length === 0 && !mockResources) {
    return (
      <div className="h-full flex flex-col items-center justify-center bg-[var(--bg-primary)] p-8">
        <AlertCircle className="h-8 w-8 text-red-500 mb-4" />
        <p className="text-sm text-[var(--text-primary)] mb-2">Failed to load resources</p>
        <p className="text-xs text-[var(--text-secondary)] mb-4">{error}</p>
        <Button
          variant="outline"
          size="sm"
          onClick={fetchResources}
          className="text-xs"
        >
          <RefreshCw className="h-3 w-3 mr-2" />
          Retry
        </Button>
      </div>
    );
  }

  // Show empty state when no resources deployed (but not if we have mockResources)
  if (projectId && resources.length === 0 && !isLoading && !mockResources) {
    return <ResourcesEmptyState />;
  }

  return (
    <div className="h-full flex flex-col bg-[var(--bg-primary)]">
      {/* Filters and Search */}
      <div className="border-b border-[var(--border-color)] p-4 space-y-3">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--text-secondary)]" />
            <Input
              placeholder="Search resources..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-8 pl-9 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
            />
          </div>
          <Select value={environment} onValueChange={setEnvironment}>
            <SelectTrigger className="h-8 w-[130px] text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
              <SelectValue>
                {environment === 'dev' ? 'Development' : environment === 'staging' ? 'Staging' : environment === 'prod' ? 'Production' : environment}
              </SelectValue>
            </SelectTrigger>
            <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
              <SelectItem value="dev" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">Development</SelectItem>
              <SelectItem value="staging" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">Staging</SelectItem>
              <SelectItem value="prod" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">Production</SelectItem>
            </SelectContent>
          </Select>
          {projectId && (
            <Button
              variant="outline"
              size="sm"
              onClick={fetchResources}
              disabled={isLoading}
              className="h-8 px-2 border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
            >
              <RefreshCw className={cn("h-3 w-3", isLoading && "animate-spin")} />
            </Button>
          )}
          <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as ResourceStatus | "all")}>
            <SelectTrigger className="h-8 w-[120px] text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
              <Filter className="h-3 w-3 mr-1" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
              <SelectItem value="all" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">All Status</SelectItem>
              <SelectItem value="active" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">Active</SelectItem>
              <SelectItem value="pending" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">Pending</SelectItem>
              <SelectItem value="updating" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">Updating</SelectItem>
              <SelectItem value="failed" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">Failed</SelectItem>
            </SelectContent>
          </Select>
          <Select value={categoryFilter} onValueChange={(value) => setCategoryFilter(value as ResourceType | "all")}>
            <SelectTrigger className="h-8 w-[120px] text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
              <Box className="h-3 w-3 mr-1" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
              <SelectItem value="all" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">All Types</SelectItem>
              <SelectItem value="compute" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">Compute</SelectItem>
              <SelectItem value="database" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">Databases</SelectItem>
              <SelectItem value="storage" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">Storage</SelectItem>
              <SelectItem value="networking" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">Networking</SelectItem>
              <SelectItem value="security" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]">Security</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Resources List */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="max-w-5xl mx-auto space-y-3">
          {Object.keys(resourcesByCategory).map((category) => {
            const resources = resourcesByCategory[category];
            if (resources.length === 0) return null;

            const isExpanded = expandedCategories.has(category);
            const categoryActive = resources.filter((r) => r.status === "active").length;
            const categoryFailed = resources.filter((r) => r.status === "failed").length;
            const categoryUpdating = resources.filter((r) => r.status === "updating").length;
            const categoryCost = resources.reduce((sum, r) => sum + (r.cost || 0), 0);

            return (
              <div key={category} className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg overflow-hidden">
                {/* Category Header */}
                <div
                  className="p-3 cursor-pointer hover:bg-[var(--bg-tertiary)] transition-colors flex items-center justify-between"
                  onClick={() => toggleCategory(category)}
                >
                  <div className="flex items-center gap-3">
                    {/* Category Icon (AWS or GCP based on cloud provider) */}
                    <div className="flex-shrink-0">
                      <Image
                        src={cloudProvider === "aws" ? AWS_ICON : getGCPCategoryIcon(category)}
                        alt={categoryLabels[category as ResourceType] || category}
                        width={20}
                        height={20}
                        className="h-5 w-5 object-contain"
                        onError={(e) => {
                          // Fallback to lucide icon if category icon fails to load
                          const target = e.target as HTMLImageElement;
                          target.style.display = 'none';
                        }}
                      />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-[var(--text-primary)]">
                          {categoryLabels[category as ResourceType] || category}
                        </span>
                        <Badge variant="outline" className="text-[9px] text-[var(--text-secondary)] border-[var(--border-color)]">
                          {resources.length}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-[10px]">
                        <span className="text-[#10b981] flex items-center gap-1">
                          ● {categoryActive} Active
                        </span>
                        {categoryUpdating > 0 && (
                          <span className="text-amber-500 flex items-center gap-1">
                            ● {categoryUpdating} Updating
                          </span>
                        )}
                        {categoryFailed > 0 && (
                          <span className="text-red-500 flex items-center gap-1">
                            ● {categoryFailed} Failed
                          </span>
                        )}
                        {/* Temporarily hidden - pricing display */}
                        {/* <span className="text-[var(--text-secondary)] flex items-center gap-1">
                          <HandCoins className="h-3 w-3" />
                          ${categoryCost.toFixed(2)}/mo
                        </span> */}
                      </div>
                    </div>
                  </div>
                  {isExpanded ? (
                    <ChevronDown className="h-4 w-4 text-[var(--text-secondary)]" />
                  ) : (
                    <ChevronRight className="h-4 w-4 text-[var(--text-secondary)]" />
                  )}
                </div>

                {/* Resources */}
                {isExpanded && (
                  <div className="border-t border-[var(--border-color)]">
                    {resources.map((resource) => {
                      const isResourceExpanded = expandedResources.has(resource.id);
                      const statusInfo = statusConfig[resource.status];

                      return (
                        <div key={resource.id} className="border-b border-[var(--border-color)] last:border-b-0">
                          <div
                            className="p-3 cursor-pointer hover:bg-[var(--bg-tertiary)] transition-colors"
                            onClick={() => toggleResource(resource.id)}
                          >
                            <div className="flex items-start justify-between">
                              <div className="flex items-start gap-3 flex-1 min-w-0">
                                {/* GCP Service Icon */}
                                <div className="relative mt-0.5 flex-shrink-0">
                                  <Image
                                    src={getServiceIcon(resource.type, resource.cloud_provider || cloudProvider)}
                                    alt={resource.type}
                                    width={20}
                                    height={20}
                                    className="h-5 w-5 object-contain"
                                    onError={(e) => {
                                      // Fallback to category icon if service icon fails to load
                                      const target = e.target as HTMLImageElement;
                                      target.style.display = 'none';
                                    }}
                                  />
                                  {/* Status indicator overlay */}
                                  <div className={cn("absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border border-[var(--bg-tertiary)] flex items-center justify-center", statusInfo.color === "text-[#10b981]" ? "bg-[#10b981]" : statusInfo.color === "text-amber-500" ? "bg-amber-500" : statusInfo.color === "text-red-500" ? "bg-red-500" : "bg-[var(--text-secondary)]")}>
                                    {resource.status === "updating" && <Loader2 className="h-1.5 w-1.5 text-white animate-spin" />}
                                  </div>
                                </div>
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs font-medium text-[var(--text-primary)]">
                                      {resource.name}
                                    </span>
                                    <Badge variant="outline" className={cn("text-[9px] capitalize", statusInfo.bgColor, statusInfo.color)}>
                                      {resource.status}
                                    </Badge>
                                    <Badge variant="outline" className="text-[9px] text-[var(--text-secondary)] border-[var(--border-color)]">
                                      {resource.type}
                                    </Badge>
                                  </div>
                                  <div className="flex items-center gap-3 mt-1 text-[10px] text-[var(--text-secondary)]">
                                    <span className="flex items-center gap-1">
                                      <MapPin className="h-3 w-3" />
                                      {resource.region}
                                    </span>
                                    {/* Temporarily hidden - pricing display */}
                                    {/* <span className="flex items-center gap-1">
                                      <HandCoins className="h-3 w-3" />
                                      ${resource.cost.toFixed(2)}/mo
                                    </span> */}
                                    <span className="flex items-center gap-1">
                                      <Clock className="h-3 w-3" />
                                      {resource.version}
                                    </span>
                                    {resource.dependencies.length > 0 && (
                                      <span className="flex items-center gap-1">
                                        <Network className="h-3 w-3" />
                                        {resource.dependencies.length} dependencies
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </div>
                              <div className="flex items-center gap-1 ml-2">
                                {/* Temporarily hidden - test feature */}
                                {/* <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-6 w-6 p-0 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setTestingResource(resource);
                                  }}
                                  title="Test resource"
                                >
                                  <SquareDashedMousePointer className="h-3 w-3" />
                                </Button> */}
                                {isResourceExpanded ? (
                                  <ChevronDown className="h-4 w-4 text-[var(--text-secondary)]" />
                                ) : (
                                  <ChevronRight className="h-4 w-4 text-[var(--text-secondary)]" />
                                )}
                              </div>
                            </div>
                          </div>

                          {/* Expanded Resource Details */}
                          {isResourceExpanded && (
                            <div className="bg-[var(--bg-tertiary)] p-4 space-y-3">
                              <div className="grid grid-cols-2 gap-4">
                                <div>
                                  <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase">ARN</label>
                                  <p className="text-xs text-[var(--text-primary)] font-mono mt-1 break-all">
                                    {resource.arn}
                                  </p>
                                </div>
                                <div>
                                  <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase">Created</label>
                                  <p className="text-xs text-[var(--text-primary)] mt-1">
                                    {new Date(resource.created_at).toLocaleDateString()}
                                  </p>
                                </div>
                                <div>
                                  <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase">Last Updated</label>
                                  <p className="text-xs text-[var(--text-primary)] mt-1">
                                    {new Date(resource.updated_at).toLocaleDateString()}
                                  </p>
                                </div>
                                <div>
                                  <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase">Version</label>
                                  <p className="text-xs text-[var(--text-primary)] mt-1">{resource.version}</p>
                                </div>
                              </div>

                              {resource.dependencies.length > 0 && (
                                <div>
                                  <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase">Dependencies</label>
                                  <div className="flex flex-wrap gap-1 mt-1">
                                    {resource.dependencies.map((dep) => (
                                      <Badge
                                        key={dep}
                                        variant="outline"
                                        className="text-[9px] text-[var(--text-primary)] border-[var(--border-color)]"
                                      >
                                        {dep}
                                      </Badge>
                                    ))}
                                  </div>
                                </div>
                              )}

                              <div>
                                <label className="text-[10px] font-medium text-[var(--text-secondary)] uppercase">Metadata</label>
                                <div className="mt-1 bg-[var(--bg-secondary)] rounded p-2">
                                  <pre className="text-[10px] font-mono text-[var(--text-primary)]">
                                    {JSON.stringify(resource.metadata, null, 2)}
                                  </pre>
                                </div>
                              </div>

                              <div className="flex items-center gap-2 pt-2">
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="h-7 text-xs border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
                                >
                                  <ExternalLink className="h-3 w-3 mr-1" />
                                  View in GCP Console
                                </Button>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="h-7 text-xs border-red-500/30 text-red-500 hover:bg-red-500/10 ml-auto"
                                >
                                  <Trash2 className="h-3 w-3 mr-1" />
                                  Delete Resource
                                </Button>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Temporarily hidden - test feature */}
      {/* {testingResource && (
        <TestResourceDialog
          resource={testingResource}
          open={!!testingResource}
          onClose={() => setTestingResource(null)}
        />
      )} */}
    </div>
  );
}
