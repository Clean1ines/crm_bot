import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAppStore } from "../../app/store";
import { useMediaQuery } from "../../shared/lib/hooks/useMediaQuery";
import { DialogList } from "./components/DialogList";
import { ChatWindow } from "./components/ChatWindow";
import { Inspector } from "./components/Inspector";

type MobileDialogsView = "list" | "chat" | "inspector";
const MOBILE_BREAKPOINT = "(max-width: 768px)";
const COMPACT_DIALOGS_BREAKPOINT = "(max-width: 1080px)";
const COLLAPSED_INSPECTOR_BREAKPOINT = "(max-width: 1360px)";

export const DialogsPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const isMobile = useMediaQuery(MOBILE_BREAKPOINT);
  const isCompactDialogs = useMediaQuery(COMPACT_DIALOGS_BREAKPOINT);
  const isInspectorCollapsed = useMediaQuery(COLLAPSED_INSPECTOR_BREAKPOINT);
  const {
    selectedThreadId,
    setSelectedThreadId,
    setSelectedThreadClient,
    clearMessages,
  } = useAppStore();
  const [mobileView, setMobileView] = useState<MobileDialogsView>("list");

  useEffect(() => {
    if (!projectId) {
      navigate("/projects");
    }
  }, [projectId, navigate]);

  useEffect(() => {
    if (projectId) {
      setSelectedThreadId(null);
      setSelectedThreadClient(null);
      clearMessages();
    }
  }, [projectId, setSelectedThreadId, setSelectedThreadClient, clearMessages]);

  if (!projectId) return null;

  const resolvedMobileView: MobileDialogsView = selectedThreadId
    ? mobileView
    : "list";

  if (isMobile) {
    return (
      <div
        key={`mobile-dialogs-${projectId}`}
        className="h-full min-h-0 bg-[var(--bg-primary)]"
      >
        {resolvedMobileView === "list" && (
          <DialogList
            key={`dialoglist-mobile-${projectId}`}
            projectId={projectId}
            mobile
            onThreadSelect={() => setMobileView("chat")}
          />
        )}

        {resolvedMobileView === "chat" && (
          <ChatWindow
            key={`chatwindow-mobile-${projectId}-${selectedThreadId || "empty"}`}
            threadId={selectedThreadId}
            projectId={projectId}
            mobile
            showBackButton
            showInspectorButton
            onBack={() => setMobileView("list")}
            onOpenInspector={() => setMobileView("inspector")}
          />
        )}

        {resolvedMobileView === "inspector" && (
          <Inspector
            key={`inspector-mobile-${projectId}-${selectedThreadId || "empty"}`}
            threadId={selectedThreadId}
            projectId={projectId}
            mobile
            onBack={() => setMobileView("chat")}
          />
        )}
      </div>
    );
  }

  if (isCompactDialogs) {
    const showList = resolvedMobileView === "list" || !selectedThreadId;

    return (
      <div className="h-full min-h-0 bg-[var(--bg-primary)]">
        {showList && (
          <div className="h-full min-h-0 overflow-hidden">
            <DialogList
              key={`dialoglist-compact-${projectId}`}
              projectId={projectId}
              onThreadSelect={() => setMobileView("chat")}
            />
          </div>
        )}

        {!showList && resolvedMobileView === "chat" && (
          <div className="h-full min-h-0 overflow-hidden">
            <ChatWindow
              key={`chatwindow-compact-${projectId}-${selectedThreadId || "empty"}`}
              threadId={selectedThreadId}
              projectId={projectId}
              showBackButton
              showInspectorButton
              onBack={() => setMobileView("list")}
              onOpenInspector={() => setMobileView("inspector")}
            />
          </div>
        )}

        {!showList && resolvedMobileView === "inspector" && (
          <div className="h-full min-h-0 overflow-hidden">
            <Inspector
              key={`inspector-compact-${projectId}-${selectedThreadId || "empty"}`}
              threadId={selectedThreadId}
              projectId={projectId}
              mobile
              onBack={() => setMobileView("chat")}
            />
          </div>
        )}
      </div>
    );
  }

  if (isInspectorCollapsed) {
    return (
      <div className="grid h-full min-h-0 grid-cols-[minmax(260px,320px)_minmax(0,1fr)] bg-[var(--bg-primary)]">
        <div className="min-w-0 overflow-hidden">
          <DialogList
            key={`dialoglist-medium-${projectId}`}
            projectId={projectId}
          />
        </div>

        <div className="min-w-0 overflow-hidden">
          {resolvedMobileView === "inspector" ? (
            <Inspector
              key={`inspector-medium-${projectId}-${selectedThreadId || "empty"}`}
              threadId={selectedThreadId}
              projectId={projectId}
              mobile
              onBack={() => setMobileView("chat")}
            />
          ) : (
            <ChatWindow
              key={`chatwindow-medium-${projectId}`}
              threadId={selectedThreadId}
              projectId={projectId}
              showInspectorButton
              onOpenInspector={() => setMobileView("inspector")}
            />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="grid h-full min-h-0 grid-cols-[minmax(260px,320px)_minmax(0,1fr)_minmax(280px,320px)] bg-[var(--bg-primary)]">
      <div className="min-w-0 overflow-hidden">
        <DialogList key={`dialoglist-${projectId}`} projectId={projectId} />
      </div>

      <div className="min-w-0 overflow-hidden">
        <ChatWindow
          key={`chatwindow-${projectId}`}
          threadId={selectedThreadId}
          projectId={projectId}
        />
      </div>

      <div className="min-w-0 overflow-hidden">
        <Inspector
          key={`inspector-${projectId}`}
          threadId={selectedThreadId}
          projectId={projectId}
        />
      </div>
    </div>
  );
};
