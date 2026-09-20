"use client";

import React from "react";
import { Sidebar } from "@/components/layout/Sidebar";

interface AppShellProps {
  children: React.ReactNode;
  /** Optional top bar slot (e.g. LiveKit Topbar on voice room). */
  topbar?: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({ children, topbar }) => {
  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      <Sidebar />
      <div className="flex-1 flex flex-col h-full overflow-hidden min-w-0">
        {topbar}
        <main className="flex-1 overflow-y-auto overflow-x-hidden">{children}</main>
      </div>
    </div>
  );
};
