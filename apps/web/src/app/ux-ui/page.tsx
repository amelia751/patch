"use client";

import { useState, useEffect } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Cloud } from "lucide-react";
import { AWSConnectionUX } from "@/components/interface/ux-ui/aws-connection-ux";

export default function UXUIPage() {
  const [currentEnvironment, setCurrentEnvironment] = useState("dev");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const availableEnvironments = ["dev", "staging", "prod"];

  return (
    <div className="h-full flex flex-col">
      <Tabs defaultValue="configure" className="h-full flex flex-col">
        {/* Header */}
        <div className="border-b border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-2 transition-colors">
          <div className="flex items-center justify-between mb-2">
            <h1 className="text-base font-semibold text-[var(--text-primary)]">AWS Multi-Environment UX Preview</h1>
            <Select value={currentEnvironment} onValueChange={setCurrentEnvironment}>
              <SelectTrigger className="w-[140px] h-7 text-xs bg-[var(--bg-secondary)] border-[var(--border-color)] text-[var(--text-primary)]">
                <SelectValue>
                  {currentEnvironment === 'dev' ? 'Development' : currentEnvironment === 'staging' ? 'Staging' : currentEnvironment === 'prod' ? 'Production' : currentEnvironment}
                </SelectValue>
              </SelectTrigger>
              <SelectContent className="bg-[var(--bg-primary)] border-[var(--border-color)]">
                {availableEnvironments.map((env) => (
                  <SelectItem
                    key={env}
                    value={env}
                    className="text-xs text-[var(--text-primary)] focus:bg-[var(--bg-tertiary)] focus:text-[var(--text-primary)]"
                  >
                    {env === 'dev' ? 'Development' : env === 'staging' ? 'Staging' : env === 'prod' ? 'Production' : env}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <TabsList className="inline-flex w-full h-9 items-center justify-between rounded-lg bg-[var(--bg-secondary)] p-1 text-[var(--text-secondary)] transition-colors">
            <TabsTrigger
              value="configure"
              className="flex-1 inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-[11px] font-medium transition-all data-[state=active]:bg-[var(--bg-primary)] data-[state=active]:text-[var(--text-tertiary)] data-[state=active]:shadow relative"
            >
              <Cloud className="w-3 h-3 mr-2" />
              Configure
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="configure" className="flex-1 m-0 p-0 overflow-hidden">
          <AWSConnectionUX />
        </TabsContent>
      </Tabs>
    </div>
  );
}
