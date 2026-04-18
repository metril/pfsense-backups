// Imperative confirmation modal.
//
// Replaces ``window.confirm`` calls — which look like OS popups, can't be
// styled, and are blocked by some browsers — with an in-app ``Dialog``.
//
// Usage:
//
//   const confirm = useConfirm();
//   const ok = await confirm({
//     title: "Delete router-prod?",
//     description: "This also removes all backup rows.",
//     confirmLabel: "Delete",
//     tone: "danger",
//   });
//   if (!ok) return;
//
// The provider is mounted once near the root so a single modal surface
// renders at a time. The promise resolves to true/false when the user
// clicks confirm/cancel (or dismisses the dialog).

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Button } from "./Button";
import { Dialog } from "./Dialog";

type Tone = "default" | "danger";

export interface ConfirmOptions {
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: Tone;
}

type ConfirmFn = (opts: ConfirmOptions) => Promise<boolean>;

const Ctx = createContext<ConfirmFn | null>(null);

interface OpenState extends ConfirmOptions {
  resolve: (v: boolean) => void;
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<OpenState | null>(null);
  // Latest-resolver ref so "X" close or overlay dismiss always resolves false
  // even when the state setter has already cleared the payload.
  const pendingRef = useRef<((v: boolean) => void) | null>(null);

  const confirm = useCallback<ConfirmFn>((opts) => {
    return new Promise<boolean>((resolve) => {
      pendingRef.current = resolve;
      setState({ ...opts, resolve });
    });
  }, []);

  function finish(result: boolean) {
    const resolver = pendingRef.current;
    pendingRef.current = null;
    setState(null);
    resolver?.(result);
  }

  const dangerous = state?.tone === "danger";

  return (
    <Ctx.Provider value={confirm}>
      {children}
      {state && (
        <Dialog
          open
          onOpenChange={(o) => {
            if (!o) finish(false);
          }}
          title={state.title}
          description={state.description}
          className="max-w-md"
        >
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => finish(false)}>
              {state.cancelLabel ?? "Cancel"}
            </Button>
            <Button
              onClick={() => finish(true)}
              className={
                dangerous
                  ? "bg-danger text-accent-fg hover:bg-danger/90"
                  : undefined
              }
              autoFocus
            >
              {state.confirmLabel ?? "Confirm"}
            </Button>
          </div>
        </Dialog>
      )}
    </Ctx.Provider>
  );
}

export function useConfirm(): ConfirmFn {
  const ctx = useContext(Ctx);
  if (ctx === null) {
    throw new Error("useConfirm must be used inside <ConfirmProvider>");
  }
  return useMemo(() => ctx, [ctx]);
}
