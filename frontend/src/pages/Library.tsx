import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Library as LibraryIcon, MoreVertical, RotateCcw, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import AppHeader from "@/components/AppHeader";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { completeCourse, getCourses, getSearch, resetCourseProgress, type CourseCard } from "@/api";

function pct(c: CourseCard) {
  return c.lectureCount ? Math.round((c.completedCount / c.lectureCount) * 100) : 0;
}

function CourseMenu({ c }: { c: CourseCard }) {
  const qc = useQueryClient();
  const [confirmReset, setConfirmReset] = useState(false);
  const invalidate = () => qc.invalidateQueries({ queryKey: ["courses"] });

  const reset = useMutation({
    mutationFn: () => resetCourseProgress(c.slug),
    onSuccess: () => {
      invalidate();
      toast.success(`Reset progress for “${c.title}”`);
    },
    onError: () => toast.error("Couldn’t reset progress"),
  });
  const complete = useMutation({
    mutationFn: () => completeCourse(c.slug),
    onSuccess: () => {
      invalidate();
      toast.success(`Marked “${c.title}” complete`);
    },
    onError: () => toast.error("Couldn’t update video"),
  });

  const hasProgress = c.completedCount > 0 || !!c.lastActivity;

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Options"
            className="size-8 bg-black/50 text-white opacity-0 backdrop-blur transition hover:bg-black/70 hover:text-white focus-visible:opacity-100 group-hover:opacity-100 data-[state=open]:opacity-100"
            onClick={(e) => e.preventDefault()}
          >
            <MoreVertical className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => complete.mutate()}>
            <Check /> Mark all watched
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            className="text-destructive focus:text-destructive"
            disabled={!hasProgress}
            onSelect={() => setConfirmReset(true)}
          >
            <RotateCcw /> Reset progress
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <AlertDialog open={confirmReset} onOpenChange={setConfirmReset}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reset progress?</AlertDialogTitle>
            <AlertDialogDescription>
              This clears your watch position and completion for every video in “{c.title}”. It can’t be
              undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => reset.mutate()}
            >
              Reset progress
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

function CourseCardView({ c }: { c: CourseCard }) {
  const p = pct(c);
  const previews = c.previews ?? [];
  const [frame, setFrame] = useState(-1);
  const timer = useRef<number | null>(null);

  const stopHover = () => {
    if (timer.current !== null) {
      window.clearInterval(timer.current);
      timer.current = null;
    }
    setFrame(-1);
  };
  const startHover = () => {
    if (previews.length === 0) return;
    previews.forEach((src) => {
      const img = new Image();
      img.src = src; // warm the cache so cycling is smooth
    });
    let i = 0;
    setFrame(0);
    timer.current = window.setInterval(() => {
      i = (i + 1) % previews.length;
      setFrame(i);
    }, 600);
  };
  useEffect(() => stopHover, []); // clear the interval on unmount

  return (
    <div
      className="group relative overflow-hidden rounded-lg border bg-card transition hover:border-primary/50 hover:shadow-md"
      onMouseEnter={startHover}
      onMouseLeave={stopHover}
    >
      <div className="absolute right-2 top-2 z-10">
        <CourseMenu c={c} />
      </div>
      <Link to={`/watch/${encodeURIComponent(c.slug)}`} className="block">
        <div className="relative aspect-video bg-muted">
          {c.cover ? (
            <img src={c.cover} alt="" loading="lazy" className="h-full w-full object-cover" />
          ) : (
            <div className="grid h-full w-full place-items-center bg-gradient-to-br from-muted to-accent text-muted-foreground">
              <LibraryIcon className="size-7 opacity-40" />
            </div>
          )}
          {frame >= 0 && previews[frame] && (
            <img
              src={previews[frame]}
              alt=""
              className="absolute inset-0 h-full w-full object-cover"
            />
          )}
          {c.category && (
            <Badge variant="muted" className="absolute left-2 top-2 bg-black/60 text-white backdrop-blur">
              {c.category}
            </Badge>
          )}
          {c.completedCount > 0 && (
            <div className="absolute inset-x-0 bottom-0 h-1 bg-black/30">
              <div className="h-full bg-primary" style={{ width: `${p}%` }} />
            </div>
          )}
        </div>
        <div className="p-3">
          <div className="line-clamp-2 font-medium leading-snug">{c.title}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {c.completedCount > 0 ? `${c.completedCount}/${c.lectureCount} · ${p}%` : `${c.lectureCount} videos`}
          </div>
        </div>
      </Link>
    </div>
  );
}

export default function Library() {
  const { data, isLoading, isError } = useQuery({ queryKey: ["courses"], queryFn: getCourses });
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("All");
  const [provider, setProvider] = useState("All");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState("title");
  const query = q.trim();
  const searching = query.length >= 2;
  const selectCls =
    "h-8 rounded-md border border-input bg-background px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

  const { data: search } = useQuery({
    queryKey: ["search", query],
    queryFn: () => getSearch(query),
    enabled: searching,
  });

  const browse = useMemo(
    () =>
      (data?.courses ?? []).filter(
        (c) =>
          (cat === "All" || c.category === cat) &&
          (provider === "All" || c.provider === provider),
      ),
    [data, cat, provider],
  );

  const view = useMemo(() => {
    const list = browse.filter((c) => {
      if (status === "all") return true;
      const completed = c.lectureCount > 0 && c.completedCount === c.lectureCount;
      const inProgress = !completed && (c.completedCount > 0 || !!c.lastActivity);
      if (status === "completed") return completed;
      if (status === "inprogress") return inProgress;
      return !completed && !inProgress; // notstarted
    });
    const prog = (c: CourseCard) => (c.lectureCount ? c.completedCount / c.lectureCount : 0);
    return [...list].sort((a, b) => {
      if (sort === "title") return a.title.localeCompare(b.title);
      if (sort === "watched") return (b.lastActivity ?? "").localeCompare(a.lastActivity ?? "");
      if (sort === "added") return (b.createdAt ?? "").localeCompare(a.createdAt ?? "");
      return prog(b) - prog(a); // progress desc
    });
  }, [browse, status, sort]);
  const continueRow = useMemo(
    () =>
      (data?.courses ?? [])
        .filter((c) => c.lastActivity && c.completedCount < c.lectureCount)
        .sort((a, b) => (b.lastActivity ?? "").localeCompare(a.lastActivity ?? ""))
        .slice(0, 6),
    [data],
  );
  const bySlug = useMemo(() => {
    const m = new Map<string, CourseCard>();
    (data?.courses ?? []).forEach((c) => m.set(c.slug, c));
    return m;
  }, [data]);

  const results = search?.results ?? [];
  const courseHits = results.filter((r) => r.kind === "course");
  const lessonHits = results.filter((r) => r.kind === "lecture");

  return (
    <div className="min-h-screen">
      <AppHeader
        center={
          <div className="relative w-full max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="Search videos…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
        }
      />

      <main className="mx-auto w-full max-w-[1700px] px-4 py-6 md:px-6">
        {isLoading && <p className="text-muted-foreground">Loading library…</p>}
        {isError && <p className="text-destructive">Couldn’t reach the backend.</p>}

        {searching ? (
          <div className="space-y-8">
            {courseHits.length > 0 && (
              <section>
                <h2 className="mb-3 text-lg font-semibold">Videos</h2>
                <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
                  {courseHits.map((r) => {
                    const c = bySlug.get(r.slug);
                    return c ? <CourseCardView key={`c${r.refId}`} c={c} /> : null;
                  })}
                </div>
              </section>
            )}
            <section>
              <h2 className="mb-3 text-lg font-semibold">In collections</h2>
              {lessonHits.length === 0 ? (
                <p className="text-muted-foreground">No videos match.</p>
              ) : (
                <div className="divide-y rounded-lg border">
                  {lessonHits.map((r) => (
                    <Link
                      key={`l${r.refId}`}
                      to={`/watch/${encodeURIComponent(r.slug)}?lecture=${r.refId}`}
                      className="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-accent"
                    >
                      <span className="font-medium">{r.title}</span>
                      <span className="truncate text-sm text-muted-foreground">{r.context}</span>
                    </Link>
                  ))}
                </div>
              )}
            </section>
          </div>
        ) : (
          <div className="md:grid md:grid-cols-[14rem_minmax(0,1fr)] md:gap-8">
            {/* Filters sidebar */}
            {data && data.courses.length > 0 && (
              <aside className="mb-6 md:mb-0">
                <div className="space-y-5 md:sticky md:top-[4.5rem]">
                  <div>
                    <div className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Topic
                    </div>
                    <div className="flex flex-wrap gap-1.5 md:max-h-[58vh] md:flex-col md:flex-nowrap md:gap-0.5 md:overflow-y-auto md:pr-1">
                      {["All", ...data.categories].map((c) => (
                        <button
                          key={c}
                          onClick={() => setCat(c)}
                          className={cn(
                            "rounded-md px-2.5 py-1.5 text-left text-sm transition-colors",
                            c === cat
                              ? "bg-primary font-medium text-primary-foreground"
                              : "text-muted-foreground hover:bg-accent hover:text-foreground",
                          )}
                        >
                          {c}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-2">
                    {(data.providers ?? []).length >= 2 && (
                      <select
                        className={cn(selectCls, "w-full")}
                        value={provider}
                        onChange={(e) => setProvider(e.target.value)}
                      >
                        <option value="All">All providers</option>
                        {(data.providers ?? []).map((p) => (
                          <option key={p} value={p}>
                            {p}
                          </option>
                        ))}
                      </select>
                    )}
                    <select
                      className={cn(selectCls, "w-full")}
                      value={status}
                      onChange={(e) => setStatus(e.target.value)}
                    >
                      <option value="all">All videos</option>
                      <option value="inprogress">In progress</option>
                      <option value="completed">Watched</option>
                      <option value="notstarted">Not started</option>
                    </select>
                    <select
                      className={cn(selectCls, "w-full")}
                      value={sort}
                      onChange={(e) => setSort(e.target.value)}
                    >
                      <option value="title">Sort: A–Z</option>
                      <option value="watched">Sort: Recently watched</option>
                      <option value="added">Sort: Recently added</option>
                      <option value="progress">Sort: Progress</option>
                    </select>
                  </div>
                </div>
              </aside>
            )}

            {/* Content */}
            <div className="min-w-0 space-y-8">
              {continueRow.length > 0 && (
                <section>
                  <h2 className="mb-3 text-lg font-semibold">Continue watching</h2>
                  <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
                    {continueRow.map((c) => <CourseCardView key={c.id} c={c} />)}
                  </div>
                </section>
              )}

              {data && data.courses.length === 0 ? (
                <div className="grid place-items-center rounded-lg border border-dashed py-16 text-center">
                  <LibraryIcon className="mb-3 size-8 text-muted-foreground" />
                  <p className="font-medium">No videos yet</p>
                  <p className="mb-4 text-sm text-muted-foreground">
                    Add a library that points at a folder of your videos.
                  </p>
                  <Button asChild>
                    <Link to="/settings">Add a library</Link>
                  </Button>
                </div>
              ) : view.length === 0 ? (
                <p className="py-10 text-center text-muted-foreground">No videos match these filters.</p>
              ) : (
                <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
                  {view.map((c) => <CourseCardView key={c.id} c={c} />)}
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
