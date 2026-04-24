import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  Check,
  ClipboardCopy,
  Clock,
  Download,
  History,
  Pencil,
  Split,
  Tag as TagIcon,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Tabs } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/Toast";
import {
  useAnchorBlameSummary,
  useBackups,
  useInstances,
  useParsedBackup,
  useUpdateBackup,
} from "@/api/queries";
import { api, triggerDownload } from "@/api/client";
import { useFocusedAnchor } from "@/lib/useFocusedAnchor";
import { useBlameHotkey } from "@/lib/useBlameHotkey";
import { expandThenScrollToHash } from "@/lib/xref";
import { AnchorHistoryDrawer } from "@/components/xref/AnchorHistoryDrawer";
import {
  AnchorBlameProvider,
  blameTooltipText,
} from "@/components/xref/AnchorBlame";
import { ReturnToBackupPill } from "@/components/nav/ReturnToBackupPill";

const MonacoViewer = lazy(() => import("@/components/MonacoViewer"));
const ParsedBackupView = lazy(() =>
  import("@/components/ParsedBackupView").then((m) => ({
    default: m.ParsedBackupView,
  })),
);

type ViewTab = "structured" | "raw";

interface BackupDetail {
  id: number;
  instance_id: number;
  started_at: string;
  finished_at: string;
  duration_seconds: number;
  filename: string;
  path: string;
  size_bytes: number;
  compressed: boolean;
  success: boolean;
  error_message: string | null;
  tag: string | null;
  note: string | null;
}

export function BackupViewPage() {
  const { id: idParam } = useParams();
  const id = Number(idParam);
  const nav = useNavigate();
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  // ``?anchor=…`` — drawer jump-to-source target (scroll + flash on
  // mount, then stripped). ``?from=…`` — originating backup id so
  // ``ReturnToBackupPill`` can offer a one-click return.
  const anchorParam = searchParams.get("anchor");
  const fromParam = searchParams.get("from");
  const fromBackupId = fromParam ? Number(fromParam) : null;

  const [detail, setDetail] = useState<BackupDetail | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const instances = useInstances();
  // Pull the sibling list AFTER we know which instance this backup belongs to
  // so "Diff against previous" can find the immediate predecessor.
  const siblings = useBackups(detail?.instance_id);
  const updateBackup = useUpdateBackup();

  const [editingMeta, setEditingMeta] = useState(false);
  const [tagDraft, setTagDraft] = useState("");
  const [noteDraft, setNoteDraft] = useState("");
  const [tab, setTab] = useState<ViewTab>("structured");

  // ---- Structured ↔ Raw XML tab-switch sync ----
  //
  // Track which anchor the operator is currently reading:
  //   - On the Structured tab: the nearest visible xref-/field- row.
  //   - On the Raw XML tab: the Monaco cursor's line, mapped back
  //     through the positions map to the enclosing anchor.
  //
  // On tab switch, translate the current ``focusedAnchor`` to the
  // other tab's coordinate system so the operator lands on the same
  // content.
  const { data: parsedResponse } = useParsedBackup(id);
  const positions = parsedResponse?.positions;
  const [focusedAnchor, setFocusedAnchor] = useState<string | null>(null);
  const [rawFocusLine, setRawFocusLine] = useState<number | undefined>(undefined);

  // Structured-view tracker: only observes while the Structured tab
  // is mounted. Updates ``focusedAnchor`` whenever the nearest
  // visible row changes. Disabled while Raw XML is active (that tab
  // drives ``focusedAnchor`` via ``onCursorLineChange``).
  const structuredAnchor = useFocusedAnchor(tab === "structured");
  useEffect(() => {
    if (tab === "structured" && structuredAnchor) {
      setFocusedAnchor(structuredAnchor);
    }
  }, [tab, structuredAnchor]);

  // Blame drawer — same ``h`` hotkey as the InstanceHistory page,
  // gated on the Structured tab so pressing ``h`` while scrolling
  // Monaco doesn't silently open blame for a stale anchor. Reuses
  // the unified ``focusedAnchor`` above (driven by either the
  // intersection observer or the Monaco cursor mapper), so blame
  // always opens on whatever the operator was most recently
  // focused on.
  const onNoBlameAnchor = useCallback(() => {
    toast.info("Scroll to a field and press h again");
  }, [toast]);
  const { blameAnchor, openBlame, closeBlame } = useBlameHotkey({
    enabled: tab === "structured",
    focusedAnchor,
    onNoAnchor: onNoBlameAnchor,
  });

  const anchorForLine = useCallback(
    (line: number): string | null => {
      if (!positions) return null;
      // Find the most-specific (= smallest range) anchor whose range
      // brackets the cursor line. Walking every entry is O(n) but
      // n is "number of rows" (hundreds, not thousands) and this
      // fires once per cursor move — negligible.
      let best: string | null = null;
      let bestSpan = Infinity;
      for (const [id, range] of Object.entries(positions)) {
        const [start, end] = range;
        if (start <= line && line <= end) {
          const span = end - start;
          if (span < bestSpan) {
            bestSpan = span;
            best = id;
          }
        }
      }
      return best;
    },
    [positions],
  );

  // v0.40.0: blame summary prefetch. Passing ``detail?.id`` as the
  // ``as_of_backup_id`` cutoff so the tooltip reflects "what had
  // changed by the time this backup was taken" — hovering on an
  // old backup shows blame up to that point, not up to now.
  const blameSummary = useAnchorBlameSummary(detail?.instance_id, detail?.id);
  const blameAnchors = blameSummary.data?.anchors;
  const blameIndexed = blameSummary.data?.indexed ?? false;

  // Monaco hover provider: map hovered line → anchor via
  // ``positions``, then look up the anchor in the blame summary.
  // Returns markdown (plain text here) or null to suppress.
  const monacoBlameProvider = useCallback(
    (line: number): string | null => {
      if (!blameIndexed || !blameAnchors) return null;
      const anchor = anchorForLine(line);
      if (!anchor) return null;
      const entry = blameAnchors[anchor];
      if (!entry) return null;
      return blameTooltipText(entry);
    },
    [anchorForLine, blameAnchors, blameIndexed],
  );

  const onMonacoCursorLine = useCallback(
    (line: number) => {
      const anchor = anchorForLine(line);
      if (anchor) setFocusedAnchor(anchor);
    },
    [anchorForLine],
  );

  // ``?anchor=…`` handling: when the operator arrives from a blame
  // drawer's "open this backup" link, scroll + flash the target row.
  // Structured is preferred (nicer visual), Raw XML is the fallback
  // when the anchor isn't rendered in Structured (filtered out,
  // collapsed section that refused to expand, etc.).
  useEffect(() => {
    if (!anchorParam || !positions) return;
    const targetId = anchorParam;

    const stripAnchorParam = () => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.delete("anchor");
          return next;
        },
        { replace: true },
      );
    };

    const range = positions[targetId];
    // Unknown anchor id (e.g. the anchor was deleted in this
    // backup): strip the param so we don't retry on every re-render.
    if (!range) {
      stripAnchorParam();
      return;
    }

    let done = false;
    let obs: MutationObserver | null = null;
    let timeoutId: number | undefined;

    const tryStructured = (): boolean => {
      const el = document.getElementById(targetId);
      if (!el) return false;
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("anchor-flash");
      window.setTimeout(() => el.classList.remove("anchor-flash"), 2000);
      (el as HTMLElement).focus?.({ preventScroll: true });
      setFocusedAnchor(targetId);
      done = true;
      stripAnchorParam();
      return true;
    };

    // Ensure Structured tab is active so the DOM node can appear.
    setTab("structured");

    if (!tryStructured()) {
      obs = new MutationObserver(() => {
        if (done) return;
        if (tryStructured()) obs?.disconnect();
      });
      obs.observe(document.body, { childList: true, subtree: true });
      // Deadline: if no matching mutation arrives within 3s (lazy
      // import took too long, row got filtered out, etc.) fall back
      // to Raw XML and let Monaco reveal the enclosing line.
      timeoutId = window.setTimeout(() => {
        if (done) return;
        done = true;
        obs?.disconnect();
        setTab("raw");
        setRawFocusLine(range[0]);
        setFocusedAnchor(targetId);
        stripAnchorParam();
      }, 3000);
    }

    return () => {
      obs?.disconnect();
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };
    // Intentionally exclude ``setSearchParams`` (stable reference
    // per react-router docs) — including it triggers redundant
    // re-runs of this effect on every URL mutation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anchorParam, positions]);

  const switchTab = useCallback(
    (next: ViewTab) => {
      if (next === tab) return;
      if (next === "raw") {
        // Structured → Raw: look up the current anchor's line range
        // and scroll Monaco to the start. Undefined clears the
        // highlight so a fresh open (no anchor yet) stays neutral.
        const range = focusedAnchor ? positions?.[focusedAnchor] : undefined;
        setRawFocusLine(range ? range[0] : undefined);
      } else {
        // Raw → Structured: bump the hash so the deep-link bridge +
        // scroll helpers land on the focused row.
        if (focusedAnchor) {
          // ``ParsedBackupView`` is React.lazy — the import can
          // take tens to hundreds of ms after tab switch, and the
          // anchor id we want to scroll to doesn't exist in the
          // DOM until then. A plain rAF defer isn't enough. Poll
          // via MutationObserver with a deadline; when the anchor
          // appears, call ``expandThenScrollToHash``. Give up after
          // 3s so a missing anchor (e.g. filtered out) doesn't leak
          // the observer forever.
          const targetId = focusedAnchor;
          const deadline = Date.now() + 3000;
          const tryScroll = (): boolean => {
            if (document.getElementById(targetId)) {
              expandThenScrollToHash(`#${targetId}`);
              return true;
            }
            return false;
          };
          if (!tryScroll()) {
            const obs = new MutationObserver(() => {
              if (tryScroll() || Date.now() > deadline) {
                obs.disconnect();
              }
            });
            obs.observe(document.body, { childList: true, subtree: true });
            window.setTimeout(() => obs.disconnect(), 3000);
          }
        }
      }
      setTab(next);
    },
    [tab, focusedAnchor, positions],
  );

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    setContent(null);
    setError(null);
    Promise.all([
      api.get<BackupDetail>(`/api/backups/${id}`),
      fetch(`/api/backups/${id}/content`, { credentials: "include" }).then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.text();
      }),
    ])
      .then(([d, c]) => {
        if (cancelled) return;
        setDetail(d);
        setContent(c);
      })
      .catch((e) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, [id]);

  const instanceName = useMemo(() => {
    if (!detail) return "";
    const inst = instances.data?.find((i) => i.id === detail.instance_id);
    return inst?.name ?? `id=${detail.instance_id}`;
  }, [instances.data, detail]);

  const previous = useMemo(() => {
    if (!detail || !siblings.data) return null;
    const olderFirst = siblings.data
      .filter((b) => b.id !== detail.id && b.success)
      .filter((b) => new Date(b.started_at) < new Date(detail.started_at))
      .sort((a, b) => (new Date(b.started_at).getTime() - new Date(a.started_at).getTime()));
    return olderFirst[0] ?? null;
  }, [detail, siblings.data]);

  async function copyToClipboard() {
    if (!content) return;
    try {
      await navigator.clipboard.writeText(content);
      toast.success("Copied XML to clipboard");
    } catch (e) {
      toast.error(String(e));
    }
  }

  async function download() {
    if (!detail) return;
    const blob = await api.downloadBlob(`/api/backups/${detail.id}/download`);
    triggerDownload(blob, detail.filename);
  }

  function startEditingMeta() {
    if (!detail) return;
    setTagDraft(detail.tag ?? "");
    setNoteDraft(detail.note ?? "");
    setEditingMeta(true);
  }

  async function saveMeta() {
    if (!detail) return;
    try {
      const r = await updateBackup.mutateAsync({
        id: detail.id,
        patch: { tag: tagDraft, note: noteDraft },
      });
      setDetail({ ...detail, tag: r.tag, note: r.note });
      setEditingMeta(false);
      toast.success("Saved tag / note");
    } catch {
      // MutationCache's onError already surfaces the error toast.
    }
  }

  if (error) return <div className="p-6 text-sm text-danger">{error}</div>;
  if (!detail || content === null)
    return <div className="p-6 text-sm text-muted-fg">Loading…</div>;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-4 border-b border-border pb-3">
        <div className="min-w-0">
          <Link
            to="/backups"
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/40 px-2 py-1 text-sm font-medium text-fg transition-colors hover:border-accent hover:bg-accent/10 hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
          >
            <ArrowLeft className="h-4 w-4 text-accent" /> Back to backups
          </Link>
          <h1 className="mt-1 text-xl font-semibold">
            {instanceName}{" "}
            <span className="text-muted-fg font-normal">
              · {new Date(detail.started_at).toLocaleString()}
            </span>
          </h1>
          <div className="mt-1 flex items-center gap-2 font-mono text-xs text-muted-fg">
            <span className="truncate">{detail.filename}</span>
            {detail.compressed && <Badge tone="muted">gz</Badge>}
            <span>·</span>
            <span>{Math.round(detail.size_bytes / 1024)} KB</span>
            <span>·</span>
            <span>{detail.duration_seconds.toFixed(1)}s</span>
            {detail.tag && !editingMeta && (
              <span className="inline-flex items-center gap-1 rounded-full border border-accent/50 bg-accent/10 px-2 py-0.5 text-xs text-accent">
                <TagIcon className="h-3 w-3" />
                {detail.tag}
              </span>
            )}
          </div>
          {detail.note && !editingMeta && (
            <p className="mt-2 max-w-2xl whitespace-pre-wrap text-sm text-muted-fg">
              {detail.note}
            </p>
          )}
          {editingMeta && (
            <div className="mt-3 flex max-w-2xl flex-col gap-2">
              <Input
                value={tagDraft}
                onChange={(e) => setTagDraft(e.target.value)}
                placeholder="Tag (e.g. pre-upgrade, known-good)"
                maxLength={64}
                aria-label="Tag"
              />
              <textarea
                value={noteDraft}
                onChange={(e) => setNoteDraft(e.target.value)}
                placeholder="Free-text note (what makes this backup interesting?)"
                rows={3}
                className="w-full rounded-md border border-border bg-bg p-2 text-sm"
                aria-label="Note"
              />
              <div className="flex gap-2">
                <Button size="sm" onClick={saveMeta} disabled={updateBackup.isPending}>
                  <Check className="h-4 w-4" /> Save
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setEditingMeta(false)}
                  disabled={updateBackup.isPending}
                >
                  <X className="h-4 w-4" /> Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
        <div className="flex shrink-0 gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={startEditingMeta}
            disabled={editingMeta}
            title="Edit tag / note"
          >
            <Pencil className="h-4 w-4" />
            Tag / note
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() =>
              previous &&
              nav(
                `/backups/diff/${previous.id}/${detail.id}?from=${detail.id}`,
              )
            }
            disabled={!previous}
            title={
              previous
                ? `Diff against ${new Date(previous.started_at).toLocaleString()}`
                : "No prior successful backup for this instance"
            }
          >
            <Split className="h-4 w-4" />
            Diff vs previous
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => nav(`/instances/${detail.instance_id}/history`)}
            title="Scrub through every backup for this instance"
          >
            <History className="h-4 w-4" />
            History
          </Button>
          {/* Both handlers are async. Prefix with ``void`` so React
              doesn't discard the returned Promise silently — any
              rejection (network 500, clipboard API denied) should at
              least reach the browser's unhandled-rejection channel. */}
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void copyToClipboard()}
          >
            <ClipboardCopy className="h-4 w-4" />
            Copy
          </Button>
          <Button size="sm" onClick={() => void download()}>
            <Download className="h-4 w-4" />
            Download
          </Button>
        </div>
      </div>

      <Tabs
        className="mt-3"
        value={tab}
        onChange={(id) => switchTab(id as ViewTab)}
        ariaLabel="Backup view"
        idPrefix="backup-view"
        items={[
          // Single shared panel — we omit aria-controls on tabs so
          // SRs don't announce a bogus 1:1 tab↔panel association.
          { id: "structured", label: "Structured" },
          { id: "raw", label: "Raw XML" },
        ]}
      />

      {tab === "structured" && (
        <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-fg">
          <Clock aria-hidden="true" className="h-3 w-3" />
          <span>Press</span>
          <kbd className="rounded border border-border bg-muted px-1 text-[10px]">
            h
          </kbd>
          <span>on a focused row or field for its history.</span>
        </div>
      )}

      <div
        id="backup-view-panel"
        role="tabpanel"
        tabIndex={0}
        aria-labelledby={`backup-view-tab-${tab}`}
        className="mt-0 flex-1 overflow-hidden rounded-b border border-t-0 border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
      >
        <Suspense
          fallback={<div className="p-6 text-sm text-muted-fg">Loading view…</div>}
        >
          {/* v0.40.0: provide the blame summary so Structured rows
              can wire up tooltips. Raw XML uses the same data via
              ``monacoBlameProvider`` below. */}
          <AnchorBlameProvider
            anchors={blameAnchors}
            indexed={blameIndexed}
            openBlame={openBlame}
          >
            {tab === "structured" ? (
              <ParsedBackupView backupId={detail.id} />
            ) : (
              <MonacoViewer
                content={content}
                focusLine={rawFocusLine}
                onCursorLineChange={onMonacoCursorLine}
                blameProvider={monacoBlameProvider}
              />
            )}
          </AnchorBlameProvider>
        </Suspense>
      </div>

      <AnchorHistoryDrawer
        instanceId={detail.instance_id}
        anchor={blameAnchor}
        currentBackupId={detail.id}
        onClose={closeBlame}
      />
      {fromBackupId && fromBackupId !== detail.id && (
        <ReturnToBackupPill fromBackupId={fromBackupId} />
      )}
    </div>
  );
}
