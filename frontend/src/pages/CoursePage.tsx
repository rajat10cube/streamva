import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, ChevronRight, FileText, Music, Paperclip, PlayCircle } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import AppHeader from "@/components/AppHeader";
import Notes from "@/components/Notes";
import Player, { type PlayerHandle } from "@/components/Player";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { getCourse, putProgress, type LectureItem } from "@/api";

interface Prog {
  positionSec: number;
  completed: boolean;
}

function KindIcon({ kind, className }: { kind: string; className?: string }) {
  const c = cn("size-4 shrink-0", className);
  if (kind === "document") return <FileText className={c} />;
  if (kind === "audio") return <Music className={c} />;
  return <PlayCircle className={c} />;
}

function fmtDur(s?: number | null): string {
  if (!s || s <= 0) return "";
  const t = Math.round(s);
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const sec = t % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
}

function fmtTotal(s: number): string {
  if (s <= 0) return "";
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export default function CoursePage() {
  const { slug = "" } = useParams();
  const [searchParams] = useSearchParams();
  const deepLinkId = searchParams.get("lecture");
  const qc = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["course", slug],
    queryFn: () => getCourse(slug),
  });

  const flat = useMemo<LectureItem[]>(
    () => (data ? data.sections.flatMap((s) => s.lectures) : []),
    [data],
  );
  const [progress, setProgress] = useState<Record<number, Prog>>({});
  const [currentId, setCurrentId] = useState<number | null>(null);
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const lastPut = useRef<{ id: number; t: number }>({ id: -1, t: 0 });
  const activeRef = useRef<HTMLButtonElement>(null);
  const playerRef = useRef<PlayerHandle>(null);
  const didInit = useRef(false);

  // reset per-course state when navigating between courses
  useEffect(() => {
    didInit.current = false;
    setCurrentId(null);
    setCollapsed(new Set());
  }, [slug]);
  const toggleSection = (id: number) =>
    setCollapsed((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  useEffect(() => {
    if (!data) return;
    const map: Record<number, Prog> = {};
    for (const s of data.sections)
      for (const l of s.lectures) map[l.id] = { positionSec: l.positionSec, completed: l.completed };
    setProgress(map);

    if (didInit.current) return;
    didInit.current = true;
    const deepId = deepLinkId ? Number(deepLinkId) : null;
    const valid = deepId && flat.some((l) => l.id === deepId) ? deepId : null;
    const initId = valid ?? data.resumeLectureId ?? data.sections[0]?.lectures[0]?.id ?? null;
    setCurrentId(initId);
    // start with only the playing lecture's section expanded
    const activeSec = data.sections.find((s) => s.lectures.some((l) => l.id === initId));
    setCollapsed(new Set(data.sections.filter((s) => s.id !== activeSec?.id).map((s) => s.id)));
  }, [data, deepLinkId, flat]);

  const current = flat.find((l) => l.id === currentId) ?? null;
  const idx = current ? flat.findIndex((l) => l.id === current.id) : -1;

  // keep the active lecture visible: expand its section, then scroll it into view
  useEffect(() => {
    if (currentId == null) return;
    const sec = data?.sections.find((s) => s.lectures.some((l) => l.id === currentId));
    if (sec) {
      setCollapsed((prev) => {
        if (!prev.has(sec.id)) return prev;
        const n = new Set(prev);
        n.delete(sec.id);
        return n;
      });
    }
    const raf = requestAnimationFrame(() =>
      activeRef.current?.scrollIntoView({ block: "nearest" }),
    );
    return () => cancelAnimationFrame(raf);
  }, [currentId, data]);

  const report = (lecId: number, pos: number, dur: number, ended: boolean) => {
    const now = Date.now();
    if (ended || lastPut.current.id !== lecId || now - lastPut.current.t > 4000) {
      lastPut.current = { id: lecId, t: now };
      void putProgress(lecId, {
        position_sec: pos,
        duration_sec: dur || null,
        completed: ended ? true : undefined,
      }).catch(() => {});
    }
    setProgress((p) => {
      const completed = p[lecId]?.completed || ended || (dur > 0 && pos / dur >= 0.9);
      return { ...p, [lecId]: { positionSec: pos, completed } };
    });
    if (ended) qc.invalidateQueries({ queryKey: ["courses"] });
  };

  const playNext = () => {
    if (idx >= 0 && idx + 1 < flat.length) setCurrentId(flat[idx + 1].id);
  };

  const toggleComplete = async () => {
    if (!current) return;
    const p = progress[current.id];
    const next = !p?.completed;
    setProgress((prev) => ({ ...prev, [current.id]: { positionSec: p?.positionSec ?? 0, completed: next } }));
    await putProgress(current.id, {
      position_sec: p?.positionSec ?? 0,
      duration_sec: current.durationSec ?? null,
      completed: next,
    }).catch(() => {});
    qc.invalidateQueries({ queryKey: ["courses"] });
  };

  if (isLoading || isError || !data) {
    return (
      <div className="flex h-screen flex-col overflow-hidden">
        <AppHeader />
        <p className={cn("container py-6", isError ? "text-destructive" : "text-muted-foreground")}>
          {isError ? "Not found." : "Loading…"}
        </p>
      </div>
    );
  }

  const completedCount = Object.values(progress).filter((p) => p.completed).length;
  const coursePct = data.lectureCount ? Math.round((completedCount / data.lectureCount) * 100) : 0;
  const totalSec = flat.reduce((a, l) => a + (l.durationSec || 0), 0);
  const curProg = current ? progress[current.id] : undefined;
  const startPosition = curProg && !curProg.completed ? curProg.positionSec : 0;

  // a loose / single video plays on its own — no collection sidebar
  if (flat.length <= 1) {
    return (
      <div className="flex flex-col md:h-screen md:overflow-hidden">
        <AppHeader />
        <main className="min-h-0 overflow-y-auto">
          <div className="mx-auto max-w-5xl p-4 md:p-6">
            {current ? (
              <>
                <Player
                  key={current.id}
                  ref={playerRef}
                  lecture={current}
                  startPosition={startPosition}
                  hideAutoplayNext
                  onProgress={(pos, dur, ended) => report(current.id, pos, dur, ended)}
                />
                <div className="mt-4 flex items-start justify-between gap-4">
                  <h1 className="text-xl font-bold leading-snug tracking-tight">{current.title}</h1>
                  <Button
                    variant={progress[current.id]?.completed ? "default" : "outline"}
                    className="shrink-0"
                    onClick={() => void toggleComplete()}
                  >
                    <Check /> {progress[current.id]?.completed ? "Completed" : "Mark complete"}
                  </Button>
                </div>
                <Notes
                  lectureId={current.id}
                  getTime={() => playerRef.current?.getCurrentTime() ?? 0}
                  onSeek={(t) => playerRef.current?.seek(t)}
                />
              </>
            ) : (
              <p className="text-muted-foreground">Loading…</p>
            )}
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex flex-col md:h-screen md:overflow-hidden">
      <AppHeader />
      <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[340px_1fr]">
        {/* curriculum — title/progress pinned, lecture list scrolls */}
        <aside className="flex min-h-0 flex-col border-b md:border-b-0 md:border-r">
          <div className="border-b px-4 py-5">
            <h1 className="text-xl font-bold leading-snug tracking-tight">{data.title}</h1>
            {data.category && <Badge variant="muted" className="mt-2.5">{data.category}</Badge>}
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
              <div className="h-full bg-primary transition-all" style={{ width: `${coursePct}%` }} />
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {completedCount}/{data.lectureCount} · {coursePct}%
              {totalSec > 0 && ` · ${fmtTotal(totalSec)}`}
            </p>
          </div>

          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3">
            {data.sections.map((s) => {
              const isCollapsed = collapsed.has(s.id);
              return (
              <div key={s.id}>
                <button
                  onClick={() => toggleSection(s.id)}
                  className="mb-1.5 flex w-full items-center gap-1 px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground transition-colors hover:text-foreground"
                >
                  <ChevronDown className={cn("size-3.5 shrink-0 transition-transform", isCollapsed && "-rotate-90")} />
                  <span className="truncate text-left">{s.title}</span>
                </button>
                {!isCollapsed && (
                <ul className="space-y-0.5">
                  {s.lectures.map((l) => {
                    const p = progress[l.id];
                    const active = l.id === currentId;
                    const dur = fmtDur(l.durationSec);
                    const partial = !p?.completed && (p?.positionSec ?? 0) > 2 && (l.durationSec ?? 0) > 0;
                    const barPct = partial ? Math.min(100, (p!.positionSec / (l.durationSec as number)) * 100) : 0;
                    return (
                      <li key={l.id}>
                        <button
                          ref={active ? activeRef : undefined}
                          onClick={() => setCurrentId(l.id)}
                          className={cn(
                            "block w-full rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                            active ? "bg-primary text-primary-foreground" : "hover:bg-accent",
                          )}
                        >
                          <div className="flex items-center gap-2">
                            {p?.completed ? (
                              <Check className={cn("size-4 shrink-0", !active && "text-primary")} />
                            ) : (
                              <KindIcon kind={l.kind} className={cn(!active && "text-muted-foreground")} />
                            )}
                            <span className="flex-1 truncate">{l.title}</span>
                            {dur && (
                              <span
                                className={cn(
                                  "shrink-0 text-xs tabular-nums",
                                  active ? "text-primary-foreground/80" : "text-muted-foreground",
                                )}
                              >
                                {dur}
                              </span>
                            )}
                          </div>
                          {partial && (
                            <div className="ml-6 mt-1 h-0.5 overflow-hidden rounded-full bg-foreground/15">
                              <div className="h-full bg-primary" style={{ width: `${barPct}%` }} />
                            </div>
                          )}
                        </button>
                      </li>
                    );
                  })}
                </ul>
                )}
              </div>
              );
            })}

            {data.attachments.length > 0 && (
              <div>
                <div className="mb-1.5 px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Resources
                </div>
                <ul className="space-y-0.5">
                  {data.attachments.map((a) => (
                    <li key={a.id} className="flex items-center gap-2 px-2 py-1.5 text-sm text-muted-foreground">
                      <Paperclip className="size-4 shrink-0" /> <span className="truncate">{a.title}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </aside>

        {/* stage */}
        <main className="min-h-0 overflow-y-auto">
          <div className="mx-auto max-w-5xl p-4 md:p-6">
            {current ? (
              <>
                <Player
                  key={current.id}
                  ref={playerRef}
                  lecture={current}
                  startPosition={startPosition}
                  onProgress={(pos, dur, ended) => report(current.id, pos, dur, ended)}
                  onEnded={playNext}
                  onNext={playNext}
                />
                <div className="mt-4 flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-lg font-medium">{current.title}</h2>
                    <p className="text-sm text-muted-foreground">
                      Video {idx + 1} of {flat.length}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Button
                      variant={progress[current.id]?.completed ? "default" : "outline"}
                      onClick={() => void toggleComplete()}
                    >
                      <Check /> {progress[current.id]?.completed ? "Completed" : "Mark complete"}
                    </Button>
                    <Button variant="secondary" onClick={playNext} disabled={idx < 0 || idx + 1 >= flat.length}>
                      Next <ChevronRight />
                    </Button>
                  </div>
                </div>
                <Notes
                  lectureId={current.id}
                  getTime={() => playerRef.current?.getCurrentTime() ?? 0}
                  onSeek={(t) => playerRef.current?.seek(t)}
                />
              </>
            ) : (
              <p className="text-muted-foreground">Select a video to begin.</p>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
