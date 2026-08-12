"use client";

import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from "react";
import { useAuth } from "./auth-context";
import { useProject } from "./project-context";

// Types matching backend responses
export interface ClarificationInfo {
  question: string;
  context: string;
  options?: string[];
}

export interface CheckpointInfo {
  phase: string;
  phase_description: string;
  section_name: string;
  section_data: Record<string, any>;
  section_status: string;
  message: string;
  stale_sections: string[];
}

export interface ChatResponse {
  response: string;
  session_id: string;
  project_id: string;
  version_id: string;
  version_status: string;
  section_states: Record<string, string>;
  current_phase: string;
  architecture: any | null;
  diff_from_parent: any | null;
  is_complete: boolean;
  needs_clarification: boolean;
  clarification: ClarificationInfo | null;
  needs_approval: boolean;
  checkpoint: CheckpointInfo | null;
}

export interface ArchitectureState {
  // Session/Project info
  sessionId: string | null;
  projectId: string | null;
  versionId: string | null;
  versionStatus: string;

  // Section states
  sectionStates: Record<string, string>;
  currentPhase: string;

  // Architecture data (progressively built)
  architecture: any | null;

  // Interaction states
  isLoading: boolean;
  needsClarification: boolean;
  clarification: ClarificationInfo | null;
  needsApproval: boolean;
  checkpoint: CheckpointInfo | null;
  isComplete: boolean;

  // Canvas tab state
  activeTab: string;

  // Error state
  error: string | null;
}

interface ArchitectureContextType {
  state: ArchitectureState;
  sendMessage: (message: string, resumeValue?: string) => Promise<void>;
  clearSession: () => void;
  setArchitecture: (architecture: any) => void;
  setActiveTab: (tab: string) => void;
}

const initialState: ArchitectureState = {
  sessionId: null,
  projectId: null,
  versionId: null,
  versionStatus: "",
  sectionStates: {},
  currentPhase: "",
  architecture: null,
  isLoading: false,
  needsClarification: false,
  clarification: null,
  needsApproval: false,
  checkpoint: null,
  isComplete: false,
  activeTab: "architecture",
  error: null,
};

const ArchitectureContext = createContext<ArchitectureContextType | undefined>(undefined);

export function ArchitectureProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<ArchitectureState>(initialState);
  const { isAuthenticated } = useAuth();
  const { currentProject } = useProject();
  
  // Track previous project ID to detect changes
  const prevProjectIdRef = useRef<string | null>(null);

  // Clear architecture when user logs out
  useEffect(() => {
    if (!isAuthenticated) {
      setState(initialState);
      prevProjectIdRef.current = null;
    }
  }, [isAuthenticated]);
  
  // Clear architecture when project changes (switch, delete, or new import)
  // This prevents stale architecture from showing on the canvas
  useEffect(() => {
    const currentProjectId = currentProject?.id || null;
    const prevProjectId = prevProjectIdRef.current;
    
    // If project changed (including going from some project to null, or to a different project)
    if (prevProjectId !== null && currentProjectId !== prevProjectId) {
      console.log(`[ArchitectureContext] Project changed from ${prevProjectId} to ${currentProjectId}, clearing architecture`);
      setState(initialState);
    }
    
    // Update ref for next comparison
    prevProjectIdRef.current = currentProjectId;
  }, [currentProject?.id]);

  const sendMessage = useCallback(async (message: string, resumeValue?: string) => {
    // Clear previous approval/clarification state while loading
    setState(prev => ({ 
      ...prev, 
      isLoading: true, 
      error: null,
      needsApproval: false,
      needsClarification: false,
    }));

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          session_id: state.sessionId,
          project_id: state.projectId,
          version_id: state.versionId,
          resume_value: resumeValue,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data: ChatResponse = await response.json();

      // Build architecture progressively from checkpoints
      // IMPORTANT: Preserve existing architecture data and merge new data
      let updatedArchitecture = state.architecture ? { ...state.architecture } : {};
      
      if (data.checkpoint) {
        const { section_name, section_data } = data.checkpoint;
        
        // Merge section data into architecture
        if (section_name === "graph") {
          updatedArchitecture = {
            ...updatedArchitecture,
            architecture_type: section_data.architecture_type,
            description: section_data.description,
            graph: {
              nodes: section_data.nodes || [],
              edges: section_data.edges || [],
            },
          };
        } else if (section_name === "api") {
          updatedArchitecture = {
            ...updatedArchitecture,
            api: { 
              roles: section_data.roles || [],
              routes: section_data.routes || [] 
            },
          };
        } else if (section_name === "database") {
          updatedArchitecture = {
            ...updatedArchitecture,
            database: {
              engine: section_data.engine,
              rationale: section_data.rationale,
              schema: { tables: section_data.tables || section_data.dynamodb_tables || [] },
            },
          };
        } else if (section_name === "constraints") {
          // Store constraints data with proper structure
          updatedArchitecture = {
            ...updatedArchitecture,
            constraints: section_data.constraints || { rules: [], validations: [] },
            risks: section_data.risks || { assumptions: [], identifiedRisks: [] },
          };
        }
      }

      // Merge complete architecture if available, but PRESERVE progressively built data
      if (data.architecture) {
        // Helper to check if an object has actual content
        const hasContent = (obj: any) => obj && Object.keys(obj).length > 0;
        const hasRules = (c: any) => c && Array.isArray(c.rules) && c.rules.length > 0;
        const hasRisks = (r: any) => r && (
          (Array.isArray(r.assumptions) && r.assumptions.length > 0) ||
          (Array.isArray(r.identifiedRisks) && r.identifiedRisks.length > 0)
        );
        
        updatedArchitecture = {
          ...updatedArchitecture,  // Start with progressively built data
          ...data.architecture,    // Merge complete architecture
          // Preserve constraints/risks from whichever source has actual data
          constraints: hasRules(data.architecture.constraints) 
            ? data.architecture.constraints 
            : (hasRules(updatedArchitecture.constraints) ? updatedArchitecture.constraints : { rules: [], validations: [] }),
          risks: hasRisks(data.architecture.risks) 
            ? data.architecture.risks 
            : (hasRisks(updatedArchitecture.risks) ? updatedArchitecture.risks : { assumptions: [], identifiedRisks: [] }),
        };
      }

      setState(prev => ({
        ...prev,
        sessionId: data.session_id,
        projectId: data.project_id,
        versionId: data.version_id,
        versionStatus: data.version_status,
        sectionStates: data.section_states,
        currentPhase: data.current_phase,
        architecture: updatedArchitecture,
        isLoading: false,
        needsClarification: data.needs_clarification,
        clarification: data.clarification,
        needsApproval: data.needs_approval,
        checkpoint: data.checkpoint,
        isComplete: data.is_complete,
      }));

    } catch (error: any) {
      console.error("Error sending message:", error);
      setState(prev => ({
        ...prev,
        isLoading: false,
        error: error.message || "Failed to send message",
      }));
    }
  }, [state.sessionId, state.projectId, state.versionId, state.architecture]);

  const clearSession = useCallback(() => {
    setState(initialState);
  }, []);

  const setArchitecture = useCallback((architecture: any) => {
    setState(prev => ({
      ...prev,
      architecture,
      isComplete: !!architecture,
    }));
  }, []);

  const setActiveTab = useCallback((tab: string) => {
    setState(prev => ({
      ...prev,
      activeTab: tab,
    }));
  }, []);

  return (
    <ArchitectureContext.Provider value={{ state, sendMessage, clearSession, setArchitecture, setActiveTab }}>
      {children}
    </ArchitectureContext.Provider>
  );
}

export function useArchitecture() {
  const context = useContext(ArchitectureContext);
  if (context === undefined) {
    throw new Error("useArchitecture must be used within an ArchitectureProvider");
  }
  return context;
}

