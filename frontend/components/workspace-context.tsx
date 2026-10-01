"use client";
import { createContext, useContext } from "react";
import type { Role, Workspace } from "@/lib/api";

export interface WorkspaceCtx {
  workspace: Workspace;
  role: Role;
  isOwner: boolean;
  reload: () => void;
}

export const WorkspaceContext = createContext<WorkspaceCtx | null>(null);

export function useWorkspace(): WorkspaceCtx {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used inside a workspace layout");
  return ctx;
}
