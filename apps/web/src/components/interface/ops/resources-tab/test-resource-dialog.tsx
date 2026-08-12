"use client";

import React, { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  Play,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  Plus,
  Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface DeployedResource {
  id: string;
  name: string;
  type: string;
  category: string;
  status: string;
  region: string;
  arn: string;
  metadata?: any;
}

interface TestResult {
  success: boolean;
  statusCode?: number;
  responseTime: number;
  data?: any;
  error?: string;
  logs?: string[];
  timestamp: string;
}

interface TestResourceDialogProps {
  resource: DeployedResource;
  open: boolean;
  onClose: () => void;
}

export function TestResourceDialog({ resource, open, onClose }: TestResourceDialogProps) {
  const [activeTab, setActiveTab] = useState<'quick' | 'advanced' | 'history'>('quick');
  const [isLoading, setIsLoading] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testParams, setTestParams] = useState<any>({});

  const handleRunTest = async () => {
    setIsLoading(true);
    setTestResult(null);

    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

      // Build test request based on resource type
      const testRequest = {
        resource_type: resource.type,
        resource_id: resource.id,
        test_type: 'quick',
        params: testParams,
        project_id: 'jetrun-ai', // TODO: Get from context
      };

      const response = await fetch(`${API_URL}/api/resources/test`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(testRequest),
        credentials: 'include',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Test failed with status ${response.status}`);
      }

      const result = await response.json();
      setTestResult(result);
    } catch (error) {
      setTestResult({
        success: false,
        error: error instanceof Error ? error.message : "Test failed",
        responseTime: 0,
        timestamp: new Date().toISOString(),
      });
    } finally {
      setIsLoading(false);
    }
  };

  const getTestInterface = () => {
    const resourceType = resource.type.toLowerCase();

    // Cloud Run / Cloud Functions - HTTP Testing
    if (resourceType.includes('cloud run') || resourceType.includes('cloud functions')) {
      return <CloudRunTestInterface resource={resource} onParamsChange={setTestParams} />;
    }

    // Firestore / Cloud SQL - Database Testing
    if (resourceType.includes('firestore') || resourceType.includes('cloud sql')) {
      return <DatabaseTestInterface resource={resource} onParamsChange={setTestParams} />;
    }

    // Cloud Storage - File Operations
    if (resourceType.includes('storage')) {
      return <StorageTestInterface resource={resource} onParamsChange={setTestParams} />;
    }

    // Pub/Sub - Messaging
    if (resourceType.includes('pub/sub') || resourceType.includes('pubsub')) {
      return <PubSubTestInterface resource={resource} onParamsChange={setTestParams} />;
    }

    // Secret Manager - Access Testing
    if (resourceType.includes('secret')) {
      return <SecretTestInterface resource={resource} onParamsChange={setTestParams} />;
    }

    // Default generic test
    return <GenericTestInterface resource={resource} />;
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl h-[85vh] flex flex-col bg-[var(--bg-primary)] border-[var(--border-color)]">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <DialogTitle className="text-[var(--text-primary)]">Test Resource</DialogTitle>
            <Badge variant="outline" className="text-[var(--text-secondary)] border-[var(--border-color)]">
              {resource.type}
            </Badge>
          </div>
          <DialogDescription className="text-[var(--text-secondary)]">
            {resource.name} • {resource.region}
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as any)} className="flex-1 flex flex-col">
          <TabsList className="bg-[var(--bg-secondary)] text-[var(--text-secondary)]">
            <TabsTrigger value="quick" className="text-xs text-[var(--text-secondary)] data-[state=active]:bg-[var(--bg-primary)] data-[state=active]:text-[var(--text-primary)]">
              Quick Test
            </TabsTrigger>
            <TabsTrigger value="advanced" className="text-xs text-[var(--text-secondary)] data-[state=active]:bg-[var(--bg-primary)] data-[state=active]:text-[var(--text-primary)]">
              Advanced
            </TabsTrigger>
            <TabsTrigger value="history" className="text-xs text-[var(--text-secondary)] data-[state=active]:bg-[var(--bg-primary)] data-[state=active]:text-[var(--text-primary)]">
              History
            </TabsTrigger>
          </TabsList>

          <TabsContent value="quick" className="flex-1 overflow-y-auto mt-4">
            {getTestInterface()}
          </TabsContent>

          <TabsContent value="advanced" className="flex-1 overflow-y-auto mt-4">
            <div className="text-sm text-[var(--text-secondary)]">
              Advanced testing features coming soon...
            </div>
          </TabsContent>

          <TabsContent value="history" className="flex-1 overflow-y-auto mt-4">
            <div className="text-sm text-[var(--text-secondary)]">
              Test history will appear here...
            </div>
          </TabsContent>
        </Tabs>

        {/* Test Results Panel */}
        {testResult && (
          <div className="border-t border-[var(--border-color)] pt-4 mt-4">
            <div className="flex items-center gap-2 mb-3">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">Response</h3>
              {testResult.success ? (
                <CheckCircle2 className="h-4 w-4 text-[#10b981]" />
              ) : (
                <XCircle className="h-4 w-4 text-red-500" />
              )}
            </div>

            <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-3 space-y-2">
              <div className="flex items-center gap-4 text-xs">
                {testResult.statusCode && (
                  <div className="flex items-center gap-1">
                    <span className="text-[var(--text-secondary)]">Status:</span>
                    <span className={cn(
                      "font-medium",
                      testResult.statusCode >= 200 && testResult.statusCode < 300 ? "text-[#10b981]" :
                      testResult.statusCode >= 400 ? "text-red-500" : "text-amber-500"
                    )}>
                      {testResult.statusCode}
                    </span>
                  </div>
                )}
                <div className="flex items-center gap-1">
                  <Clock className="h-3 w-3 text-[var(--text-secondary)]" />
                  <span className="text-[var(--text-secondary)]">{testResult.responseTime}ms</span>
                </div>
                <div className="flex items-center gap-1 text-[var(--text-secondary)] text-[10px]">
                  {new Date(testResult.timestamp).toLocaleString()}
                </div>
              </div>

              {testResult.error && (
                <div className="text-xs text-red-500 mt-2">
                  {testResult.error}
                </div>
              )}

              {testResult.data && (
                <pre className="text-xs text-[var(--text-primary)] bg-[var(--bg-primary)] p-3 rounded border border-[var(--border-color)] overflow-x-auto mt-2">
                  {JSON.stringify(testResult.data, null, 2)}
                </pre>
              )}
            </div>
          </div>
        )}

        <DialogFooter className="border-t border-[var(--border-color)] pt-4">
          <Button
            variant="outline"
            size="sm"
            onClick={onClose}
            disabled={isLoading}
            className="text-xs border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
          >
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleRunTest}
            disabled={isLoading}
            className="text-xs bg-primary hover:bg-primary/90 text-primary-foreground disabled:opacity-50"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-3.5 w-3.5 mr-2 animate-spin" />
                Testing...
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5 mr-2" />
                Run Test
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Cloud Run / Cloud Functions HTTP Testing Interface
function CloudRunTestInterface({
  resource,
  onParamsChange
}: {
  resource: DeployedResource;
  onParamsChange: (params: any) => void;
}) {
  const [method, setMethod] = useState('GET');
  const [endpoint, setEndpoint] = useState('');
  const [headers, setHeaders] = useState<Array<{ key: string; value: string }>>([
    { key: 'Content-Type', value: 'application/json' }
  ]);
  const [body, setBody] = useState('{\n  \n}');

  // Update params whenever form changes
  React.useEffect(() => {
    const headersObj = headers.reduce((acc, h) => {
      if (h.key) acc[h.key] = h.value;
      return acc;
    }, {} as Record<string, string>);

    let parsedBody = null;
    if (method === 'POST' || method === 'PUT' || method === 'PATCH') {
      try {
        parsedBody = JSON.parse(body);
      } catch {
        // Invalid JSON, will be caught by test
      }
    }

    onParamsChange({
      service_url: endpoint,
      method,
      headers: headersObj,
      body: parsedBody,
    });
  }, [method, endpoint, headers, body, onParamsChange]);

  const addHeader = () => {
    setHeaders([...headers, { key: '', value: '' }]);
  };

  const removeHeader = (index: number) => {
    setHeaders(headers.filter((_, i) => i !== index));
  };

  const updateHeader = (index: number, field: 'key' | 'value', value: string) => {
    const newHeaders = [...headers];
    newHeaders[index][field] = value;
    setHeaders(newHeaders);
  };

  return (
    <div className="space-y-4">
      {/* Method and Endpoint */}
      <div className="space-y-2">
        <Label className="text-xs text-[var(--text-secondary)]">Request</Label>
        <div className="flex gap-2">
          <Select value={method} onValueChange={setMethod}>
            <SelectTrigger className="w-[120px] h-9 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
              <SelectItem value="GET" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">GET</SelectItem>
              <SelectItem value="POST" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">POST</SelectItem>
              <SelectItem value="PUT" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">PUT</SelectItem>
              <SelectItem value="PATCH" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">PATCH</SelectItem>
              <SelectItem value="DELETE" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">DELETE</SelectItem>
            </SelectContent>
          </Select>
          <Input
            placeholder="https://service-xxx.run.app/api/endpoint"
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            className="flex-1 h-9 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
          />
        </div>
      </div>

      {/* Headers */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-xs text-[var(--text-secondary)]">Headers</Label>
          <Button
            variant="ghost"
            size="sm"
            onClick={addHeader}
            className="h-7 text-xs text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
          >
            <Plus className="h-3 w-3 mr-1" />
            Add
          </Button>
        </div>
        <div className="space-y-2">
          {headers.map((header, index) => (
            <div key={index} className="flex gap-2">
              <Input
                placeholder="Header name"
                value={header.key}
                onChange={(e) => updateHeader(index, 'key', e.target.value)}
                className="flex-1 h-8 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
              />
              <Input
                placeholder="Value"
                value={header.value}
                onChange={(e) => updateHeader(index, 'value', e.target.value)}
                className="flex-1 h-8 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
              />
              <Button
                variant="ghost"
                size="sm"
                onClick={() => removeHeader(index)}
                className="h-8 w-8 p-0 text-[var(--text-secondary)] hover:text-red-500 hover:bg-red-500/10"
              >
                <Trash2 className="h-3 w-3" />
              </Button>
            </div>
          ))}
        </div>
      </div>

      {/* Body */}
      {(method === 'POST' || method === 'PUT' || method === 'PATCH') && (
        <div className="space-y-2">
          <Label className="text-xs text-[var(--text-secondary)]">Body (JSON)</Label>
          <Textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder='{\n  "key": "value"\n}'
            className="min-h-[150px] font-mono text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
          />
        </div>
      )}

      {/* Quick Test Examples */}
      <div className="border-t border-[var(--border-color)] pt-3">
        <Label className="text-xs text-[var(--text-secondary)] mb-2 block">Quick Tests</Label>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
            onClick={() => {
              setMethod('GET');
              setEndpoint('/health');
            }}
          >
            Health Check
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
            onClick={() => {
              setMethod('GET');
              setEndpoint('/api/status');
            }}
          >
            Status
          </Button>
        </div>
      </div>
    </div>
  );
}

// Database Testing Interface (Firestore / Cloud SQL)
function DatabaseTestInterface({
  resource,
  onParamsChange
}: {
  resource: DeployedResource;
  onParamsChange: (params: any) => void;
}) {
  const [operation, setOperation] = useState('read');
  const [query, setQuery] = useState('');

  React.useEffect(() => {
    onParamsChange({
      collection: query || 'users',
      operation,
    });
  }, [operation, query, onParamsChange]);

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label className="text-xs text-[var(--text-secondary)]">Operation</Label>
        <Select value={operation} onValueChange={setOperation}>
          <SelectTrigger className="h-9 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
            <SelectItem value="read" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">Read</SelectItem>
            <SelectItem value="query" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">Query</SelectItem>
            <SelectItem value="count" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">Count</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label className="text-xs text-[var(--text-secondary)]">
          {resource.type.includes('Firestore') ? 'Collection Path' : 'Table Name'}
        </Label>
        <Input
          placeholder={resource.type.includes('Firestore') ? 'users' : 'SELECT * FROM users LIMIT 10'}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="h-9 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
        />
      </div>
    </div>
  );
}

// Cloud Storage Testing Interface
function StorageTestInterface({
  resource,
  onParamsChange
}: {
  resource: DeployedResource;
  onParamsChange: (params: any) => void;
}) {
  const [operation, setOperation] = useState('list');
  const [path, setPath] = useState('/');

  React.useEffect(() => {
    onParamsChange({
      bucket_name: resource.name,
      operation,
      prefix: path,
    });
  }, [operation, path, resource.name, onParamsChange]);

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label className="text-xs text-[var(--text-secondary)]">Operation</Label>
        <Select value={operation} onValueChange={setOperation}>
          <SelectTrigger className="h-9 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
            <SelectItem value="list" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">List Files</SelectItem>
            <SelectItem value="upload" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">Upload</SelectItem>
            <SelectItem value="download" className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)]">Download</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label className="text-xs text-[var(--text-secondary)]">Path</Label>
        <Input
          placeholder="/path/to/file"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          className="h-9 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
        />
      </div>
    </div>
  );
}

// Pub/Sub Testing Interface
function PubSubTestInterface({
  resource,
  onParamsChange
}: {
  resource: DeployedResource;
  onParamsChange: (params: any) => void;
}) {
  const [message, setMessage] = useState('{\n  "type": "test",\n  "data": "Hello World"\n}');

  React.useEffect(() => {
    let parsedMessage = {};
    try {
      parsedMessage = JSON.parse(message);
    } catch {
      // Invalid JSON
    }

    onParamsChange({
      topic_name: resource.name,
      message: parsedMessage,
    });
  }, [message, resource.name, onParamsChange]);

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label className="text-xs text-[var(--text-secondary)]">Message (JSON)</Label>
        <Textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder='{\n  "type": "notification",\n  "data": {...}\n}'
          className="min-h-[150px] font-mono text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)]"
        />
      </div>
    </div>
  );
}

// Secret Manager Testing Interface
function SecretTestInterface({
  resource,
  onParamsChange
}: {
  resource: DeployedResource;
  onParamsChange: (params: any) => void;
}) {
  React.useEffect(() => {
    onParamsChange({
      secret_name: resource.name,
      version: 'latest',
    });
  }, [resource.name, onParamsChange]);

  return (
    <div className="space-y-4">
      <div className="text-sm text-[var(--text-secondary)]">
        Test secret access and verify permissions
      </div>
      <div className="space-y-2">
        <Label className="text-xs text-[var(--text-secondary)]">Secret Name</Label>
        <Input
          value={resource.name}
          disabled
          className="h-9 text-xs bg-[var(--bg-tertiary)] border-[var(--border-color)] text-[var(--text-secondary)] cursor-not-allowed"
        />
      </div>
      <div className="space-y-2">
        <Label className="text-xs text-[var(--text-secondary)]">Version</Label>
        <Input
          value="latest"
          disabled
          className="h-9 text-xs bg-[var(--bg-tertiary)] border-[var(--border-color)] text-[var(--text-secondary)] cursor-not-allowed"
        />
      </div>
    </div>
  );
}

// Generic Testing Interface (fallback)
function GenericTestInterface({ resource }: { resource: DeployedResource }) {
  return (
    <div className="space-y-4">
      <div className="text-sm text-[var(--text-secondary)]">
        Testing interface for {resource.type} coming soon...
      </div>
      <div className="space-y-2">
        <Label className="text-xs text-[var(--text-secondary)]">Resource Information</Label>
        <div className="bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg p-4">
          <pre className="text-xs text-[var(--text-primary)] overflow-x-auto">
            {JSON.stringify(resource, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}
