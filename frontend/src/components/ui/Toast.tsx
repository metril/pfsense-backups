// Minimal toast stack. No external dep — a tiny provider + context + hook.
// Surfaces API errors (and arbitrary notices) to the user; replaces the
// silent-mutation-failure UX (H4).

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";

type Tone = "info" | "success" | "error";

interface Toast {
  id: number;
  tone: Tone;
  title?: string;
  message: string;
  timeoutMs: number;
}

interface ToastAPI {
  show: (opts: { tone?: Tone; title?: string; message: string; timeoutMs?: number }) => void;
  error: (message: string, title?: string) => void;
  success: (message: string, title?: string) => void;
  info: (message: string, title?: string) => void;
}

const Ctx = createContext<ToastAPI | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const api = useMemo<ToastAPI>(() => {
    let nextId = 1;
    function show({
      tone = "info",
      title,
      message,
      timeoutMs = 5000,
    }: {
      tone?: Tone;
      title?: string;
      message: string;
      timeoutMs?: number;
    }) {
      const id = nextId++;
      setToasts((prev) => [...prev, { id, tone, title, message, timeoutMs }]);
    }
    return {
      show,
      error: (message, title) => show({ tone: "error", title: title ?? "Error", message, timeoutMs: 8000 }),
      success: (message, title) => show({ tone: "success", title, message }),
      info: (message, title) => show({ tone: "info", title, message }),
    };
  }, []);

  return (
    <Ctx.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </Ctx.Provider>
  );
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  useEffect(() => {
    const h = setTimeout(onDismiss, toast.timeoutMs);
    return () => clearTimeout(h);
  }, [onDismiss, toast.timeoutMs]);

  return (
    <div
      role="status"
      className={cn(
        "pointer-events-auto rounded-lg border border-border bg-muted px-4 py-3 shadow-lg",
        toast.tone === "error" && "border-danger/50 bg-danger/10",
        toast.tone === "success" && "border-ok/50 bg-ok/10",
      )}
    >
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          {toast.title && <div className="text-sm font-semibold">{toast.title}</div>}
          <div className="mt-0.5 text-sm text-muted-fg break-words">{toast.message}</div>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss notification"
          className="rounded p-0.5 text-muted-fg hover:text-fg"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

export function useToast(): ToastAPI {
  const ctx = useContext(Ctx);
  if (ctx === null) {
    throw new Error("useToast must be used inside <ToastProvider>");
  }
  return ctx;
}
