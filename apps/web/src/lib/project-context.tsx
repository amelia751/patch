"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, useRef, ReactNode } from "react";
import { useAuth } from "./auth-context";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// =============================================================================
// Types
// =============================================================================

export interface Project {
  id: string;
  name: string;
  status: string;
  cloud_provider?: string;
  threadId?: string;  // Active thread ID (e.g., analysis thread)
  threadNumber?: number;  // Human-readable thread number like GitHub #1
}

interface ProjectContextType {
  projects: Project[];
  currentProject: Project | null;
  isLoading: boolean;
  setCurrentProject: (project: Project | null) => void;
  refreshProjects: () => Promise<void>;
}

// =============================================================================
// Context
// =============================================================================

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

export function useProject(): ProjectContextType {
  const context = useContext(ProjectContext);
  if (!context) {
    // Return safe defaults when not wrapped in provider
    return {
      projects: [],
      currentProject: null,
      isLoading: false,
      setCurrentProject: () => {},
      refreshProjects: async () => {},
    };
  }
  return context;
}

// =============================================================================
// Provider
// =============================================================================

interface ProjectProviderProps {
  children: ReactNode;
}

export function ProjectProvider({ children }: ProjectProviderProps) {
  const { isAuthenticated } = useAuth();
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const previousProjectsRef = useRef<string[]>([]);

  const fetchProjects = useCallback(async () => {
    if (!isAuthenticated) {
      setProjects([]);
      setCurrentProject(null);
      previousProjectsRef.current = [];
      return;
    }

    setIsLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/projects/`, {
        credentials: "include",
      });

      if (response.ok) {
        const data = await response.json();
        const projectsList: Project[] = data.projects || [];
        const previousIds = previousProjectsRef.current;
        
        // Find newly added projects (not in previous list)
        const newProjects = projectsList.filter(p => !previousIds.includes(p.id));
        
        setProjects(projectsList);
        previousProjectsRef.current = projectsList.map(p => p.id);

        // If there's a new project, select it automatically
        if (newProjects.length > 0) {
          console.log("[ProjectContext] New project detected, selecting:", newProjects[0].name);
          setCurrentProject(newProjects[0]);
        } else if (projectsList.length > 0 && !currentProject) {
          // Set first project if none selected
          setCurrentProject(projectsList[0]);
        } else if (currentProject) {
          // Verify current project still exists
          const stillExists = projectsList.some((p: Project) => p.id === currentProject.id);
          if (!stillExists && projectsList.length > 0) {
            setCurrentProject(projectsList[0]);
          } else if (!stillExists) {
            setCurrentProject(null);
          }
        }
      }
    } catch (error) {
      console.error("[ProjectContext] Failed to fetch projects:", error);
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated, currentProject]);

  // Fetch projects on auth change
  useEffect(() => {
    fetchProjects();
  }, [isAuthenticated]);

  const value: ProjectContextType = {
    projects,
    currentProject,
    isLoading,
    setCurrentProject,
    refreshProjects: fetchProjects,
  };

  return (
    <ProjectContext.Provider value={value}>
      {children}
    </ProjectContext.Provider>
  );
}

