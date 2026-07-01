import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Disc, Folder, FolderUp, KeyRound, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
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
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  addLibrary,
  browse,
  changeMyPassword,
  createUser,
  deleteLibrary,
  deleteUser,
  getBdmvDiscs,
  getBdmvStatus,
  getLibraries,
  getScanStatus,
  getUsers,
  startBdmvConvert,
  rescanAll,
  resetUserPassword,
  setUserAccess,
  type BrowseResult,
  type LibraryItem,
  type UserRow,
} from "@/api";
import { useAuth } from "@/auth";
import { cn } from "@/lib/utils";

const DESTRUCTIVE = "bg-destructive text-destructive-foreground hover:bg-destructive/90";
const errMsg = (e: unknown) => String((e as Error).message);

export default function Settings() {
  const { isAdmin } = useAuth();
  return (
    <div className="min-h-screen">
      <AppHeader />
      <main className="container max-w-4xl py-6">
        <h1 className="mb-5 text-2xl font-semibold">Settings</h1>
        <Tabs defaultValue="account">
          <TabsList>
            <TabsTrigger value="account">Account</TabsTrigger>
            {isAdmin && <TabsTrigger value="users">Users</TabsTrigger>}
            {isAdmin && <TabsTrigger value="libraries">Libraries</TabsTrigger>}
          </TabsList>
          <TabsContent value="account"><AccountTab /></TabsContent>
          {isAdmin && <TabsContent value="users"><UsersTab /></TabsContent>}
          {isAdmin && <TabsContent value="libraries"><LibrariesTab /></TabsContent>}
        </Tabs>
      </main>
    </div>
  );
}

function AccountTab() {
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await changeMyPassword(cur, next);
      setCur("");
      setNext("");
      toast.success("Password changed");
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Password</CardTitle>
        <CardDescription>Change your account password.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <div className="space-y-1.5">
            <Label>Current password</Label>
            <Input className="w-56" type="password" value={cur}
              onChange={(e) => setCur(e.target.value)} autoComplete="current-password" />
          </div>
          <div className="space-y-1.5">
            <Label>New password</Label>
            <Input className="w-56" type="password" value={next}
              onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
          </div>
          <Button type="submit" disabled={busy}>Change password</Button>
        </form>
      </CardContent>
    </Card>
  );
}

function UsersTab() {
  const qc = useQueryClient();
  const { data: users } = useQuery({ queryKey: ["users"], queryFn: getUsers });
  const { data: libs } = useQuery({ queryKey: ["libraries"], queryFn: getLibraries });
  const refresh = () => qc.invalidateQueries({ queryKey: ["users"] });

  const [u, setU] = useState("");
  const [pw, setPw] = useState("");
  const [admin, setAdmin] = useState(false);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createUser(u.trim(), pw, admin);
      setU("");
      setPw("");
      setAdmin(false);
      refresh();
      toast.success("User created");
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Users</CardTitle>
        <CardDescription>
          Manage accounts and per-library access. New users can see all libraries by default.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="divide-y rounded-lg border">
          {(users ?? []).map((user) => (
            <UserRowItem key={user.id} user={user} libs={libs ?? []} onChanged={refresh} />
          ))}
        </div>
        <form onSubmit={add} className="flex flex-wrap items-end gap-3 border-t pt-4">
          <div className="space-y-1.5">
            <Label>Username</Label>
            <Input className="w-44" value={u} onChange={(e) => setU(e.target.value)} autoComplete="off" />
          </div>
          <div className="space-y-1.5">
            <Label>Password</Label>
            <Input className="w-44" type="password" value={pw}
              onChange={(e) => setPw(e.target.value)} autoComplete="new-password" />
          </div>
          <label className="flex h-9 items-center gap-2 text-sm">
            <Checkbox checked={admin} onCheckedChange={(v) => setAdmin(v === true)} /> Admin
          </label>
          <Button type="submit"><Plus /> Add user</Button>
        </form>
      </CardContent>
    </Card>
  );
}

function UserRowItem({ user, libs, onChanged }: { user: UserRow; libs: LibraryItem[]; onChanged: () => void }) {
  const [accessOpen, setAccessOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [all, setAll] = useState(user.allLibraries);
  const [ids, setIds] = useState<number[]>(user.libraryIds);
  const [newPw, setNewPw] = useState("");

  const accessLabel = user.isAdmin || user.allLibraries
    ? "all libraries"
    : `${user.libraryIds.length} librar${user.libraryIds.length === 1 ? "y" : "ies"}`;

  const saveAccess = async () => {
    try {
      await setUserAccess(user.id, all, ids);
      setAccessOpen(false);
      onChanged();
      toast.success("Access updated");
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const doReset = async () => {
    try {
      await resetUserPassword(user.id, newPw);
      setResetOpen(false);
      setNewPw("");
      toast.success("Password reset");
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const doDelete = async () => {
    try {
      await deleteUser(user.id);
      onChanged();
      toast.success("User deleted");
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const toggle = (id: number) =>
    setIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2 font-medium">
          {user.username}
          {user.isAdmin && <Badge>admin</Badge>}
        </div>
        <div className="text-xs text-muted-foreground">{accessLabel}</div>
      </div>
      <div className="flex shrink-0 gap-2">
        {!user.isAdmin && (
          <Dialog open={accessOpen} onOpenChange={setAccessOpen}>
            <DialogTrigger asChild><Button variant="outline" size="sm">Access</Button></DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Library access — {user.username}</DialogTitle></DialogHeader>
              <label className="flex items-center gap-2 text-sm">
                <Checkbox checked={all} onCheckedChange={(v) => setAll(v === true)} /> All libraries
              </label>
              {!all && (
                <div className="max-h-60 space-y-2 overflow-y-auto rounded-md border p-3">
                  {libs.map((l) => (
                    <label key={l.id} className="flex items-center gap-2 text-sm">
                      <Checkbox checked={ids.includes(l.id)} onCheckedChange={() => toggle(l.id)} />
                      <span className="truncate">{l.name || l.path}</span>
                    </label>
                  ))}
                  {libs.length === 0 && <p className="text-sm text-muted-foreground">No libraries yet.</p>}
                </div>
              )}
              <DialogFooter><Button onClick={() => void saveAccess()}>Save</Button></DialogFooter>
            </DialogContent>
          </Dialog>
        )}

        <Dialog open={resetOpen} onOpenChange={setResetOpen}>
          <DialogTrigger asChild>
            <Button variant="outline" size="sm"><KeyRound /></Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Reset password — {user.username}</DialogTitle></DialogHeader>
            <Input type="password" placeholder="New password" value={newPw}
              onChange={(e) => setNewPw(e.target.value)} autoComplete="new-password" />
            <DialogFooter>
              <Button onClick={() => void doReset()} disabled={newPw.length < 4}>Reset password</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="destructive" size="sm"><Trash2 /></Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete {user.username}?</AlertDialogTitle>
              <AlertDialogDescription>Their account and watch progress will be removed.</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction className={DESTRUCTIVE} onClick={() => void doDelete()}>Delete</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}

function LibrariesTab() {
  const qc = useQueryClient();
  const { data: libs } = useQuery({ queryKey: ["libraries"], queryFn: getLibraries });
  const { data: scan } = useQuery({
    queryKey: ["scan-status"],
    queryFn: getScanStatus,
    refetchInterval: (q) => (q.state.data?.running ? 800 : 4000),
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["libraries"] });
    qc.invalidateQueries({ queryKey: ["courses"] });
  };

  // Blu-ray (BDMV) folders detected + conversion progress
  const { data: bdmv } = useQuery({ queryKey: ["bdmv"], queryFn: getBdmvDiscs });
  const { data: bdmvStatus } = useQuery({
    queryKey: ["bdmv-status"],
    queryFn: getBdmvStatus,
    refetchInterval: (q) => (q.state.data?.running ? 700 : false),
  });
  const converting = !!bdmvStatus?.running;
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const allTitleIds = useMemo(
    () => (bdmv?.discs ?? []).flatMap((d) => d.titles.map((t) => t.id)),
    [bdmv],
  );
  const allSelected = allTitleIds.length > 0 && allTitleIds.every((id) => selected.has(id));
  const toggleTitle = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(allTitleIds));

  const wasConverting = useRef(false);
  useEffect(() => {
    if (wasConverting.current && bdmvStatus && !bdmvStatus.running) {
      qc.invalidateQueries({ queryKey: ["bdmv"] });
      refresh();
      toast.success(`Converted ${bdmvStatus.done} title(s)`);
    }
    wasConverting.current = !!bdmvStatus?.running;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bdmvStatus?.running]);
  const startConvert = async () => {
    try {
      await startBdmvConvert([...selected]);
      setSelected(new Set());
      qc.invalidateQueries({ queryKey: ["bdmv-status"] });
      toast.success("Converting selected title(s)…");
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  // only surface errors for libraries that still exist (hide stale ones, e.g. a removed "/")
  const livePaths = new Set((libs ?? []).map((l) => l.path));
  const visibleErrors = (scan?.errors ?? []).filter((e) => livePaths.has(e.library));

  // when a scan finishes, refresh data and report the result
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && scan && !scan.running) {
      refresh();
      const errs = (scan.errors ?? []).filter((e) => (libs ?? []).some((l) => l.path === e.library));
      if (errs.length) toast.error(`Scan finished with ${errs.length} issue(s) — see below`);
      else toast.success(`Scan complete — ${scan.courses} items · ${scan.lectures} videos`);
    }
    wasRunning.current = !!scan?.running;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scan?.running]);

  const scanPct =
    scan && scan.librariesTotal > 0 ? Math.round((scan.librariesDone / scan.librariesTotal) * 100) : 0;

  const [path, setPath] = useState("/");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const add = async (p: string) => {
    const t = p.trim();
    if (!t) return;
    setBusy(true);
    try {
      await addLibrary(t, name.trim() || undefined);
      setName("");
      toast.success(`Added “${t}” — scanning…`);
      refresh();
      setTimeout(refresh, 2500);
      setTimeout(refresh, 6000);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };
  const rescan = async () => {
    await rescanAll();
    toast.success("Rescan started");
    setTimeout(refresh, 2000);
    setTimeout(refresh, 6000);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Libraries</CardTitle>
        <CardDescription>
          Folders that hold your videos. Each top-level folder becomes a collection; loose videos in
          the root play on their own. In an LXC/Docker setup, mount the host folder into the container
          first, then add its in-container path here.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="divide-y rounded-lg border">
          {(libs ?? []).map((l) => <LibraryRow key={l.id} lib={l} onChanged={refresh} />)}
          {libs && libs.length === 0 && (
            <p className="px-4 py-3 text-sm text-muted-foreground">No libraries yet — add one below.</p>
          )}
        </div>

        {scan?.running ? (
          <div className="rounded-lg border bg-muted/40 p-3 text-sm">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="truncate">
                {scan.phase === "indexing" ? "Indexing…" : `Scanning ${scan.current ?? "…"}`}
              </span>
              <span className="shrink-0 text-muted-foreground">
                {scan.librariesDone}/{scan.librariesTotal} libraries · {scan.courses} items · {scan.lectures} videos so far
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div
                className={cn("h-full bg-primary transition-all", scan.phase === "indexing" && "animate-pulse")}
                style={{ width: `${scan.phase === "indexing" ? 100 : scanPct}%` }}
              />
            </div>
          </div>
        ) : (
          scan?.finished != null && (
            <p className="text-sm text-muted-foreground">
              Last scan: {scan.courses} items · {scan.lectures} videos
              {visibleErrors.length > 0 && ` · ${visibleErrors.length} issue(s)`}
            </p>
          )
        )}

        {!scan?.running && visibleErrors.length > 0 && (
          <div className="space-y-1 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm">
            <div className="flex items-center gap-2 font-medium text-destructive">
              <AlertTriangle className="size-4" /> Last scan had issues
            </div>
            {visibleErrors.map((e, i) => (
              <div key={i} className="text-muted-foreground">
                <span className="font-mono text-foreground">{e.library}</span> — {e.error}
              </div>
            ))}
          </div>
        )}

        {(converting || (bdmv?.count ?? 0) > 0) && (
          <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm">
            {converting ? (
              <>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="truncate">Converting {bdmvStatus?.current ?? "…"}</span>
                  <span className="shrink-0 text-muted-foreground">
                    {bdmvStatus?.done}/{bdmvStatus?.total} · {bdmvStatus?.percent}%
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full bg-primary transition-all"
                    style={{ width: `${bdmvStatus?.percent ?? 0}%` }}
                  />
                </div>
              </>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">
                    {bdmv!.count} Blu-ray folder{bdmv!.count === 1 ? "" : "s"} · {bdmv!.titles} title
                    {bdmv!.titles === 1 ? "" : "s"}
                  </span>
                  <div className="flex shrink-0 gap-2">
                    <Button size="sm" variant="outline" onClick={toggleAll}>
                      {allSelected ? "Clear" : "Select all"}
                    </Button>
                    <Button size="sm" onClick={() => void startConvert()} disabled={selected.size === 0}>
                      <Disc /> Convert{selected.size ? ` (${selected.size})` : ""}
                    </Button>
                  </div>
                </div>
                <div className="max-h-72 space-y-3 overflow-y-auto pr-1">
                  {bdmv!.discs.map((d) => (
                    <div key={d.path}>
                      <div className="mb-1 truncate text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        {d.name}
                      </div>
                      <div className="space-y-1">
                        {d.titles.map((t) => (
                          <label key={t.id} className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 hover:bg-accent">
                            <Checkbox checked={selected.has(t.id)} onCheckedChange={() => toggleTitle(t.id)} />
                            <span className="flex-1 truncate">{t.label}</span>
                            {t.segments > 1 && <Badge variant="muted">{t.segments} parts</Badge>}
                            <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                              {Math.max(1, Math.round(t.durationSec / 60))}m
                            </span>
                          </label>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-end gap-3 border-t pt-4">
          <div className="min-w-[240px] flex-1 space-y-1.5">
            <Label>Path (inside the container)</Label>
            <Input value={path} onChange={(e) => setPath(e.target.value)} placeholder="/media/videos" />
          </div>
          <div className="space-y-1.5">
            <Label>Name (optional)</Label>
            <Input
              className="w-40"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="defaults to folder name"
            />
          </div>
          <BrowseDialog onSelect={setPath} onAdd={(p) => void add(p)} />
          <Button onClick={() => void add(path)} disabled={busy}>
            <Plus /> {busy ? "Adding…" : "Add"}
          </Button>
          <Button variant="outline" onClick={() => void rescan()}><RefreshCw /> Rescan all</Button>
        </div>
      </CardContent>
    </Card>
  );
}

function LibraryRow({ lib, onChanged }: { lib: LibraryItem; onChanged: () => void }) {
  const doRemove = async () => {
    try {
      await deleteLibrary(lib.id);
      onChanged();
      toast.success("Library removed");
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium">{lib.name || lib.path}</div>
        <div className="truncate text-xs text-muted-foreground">
          {lib.path} · {lib.courseCount} videos
          {!lib.accessible && <span className="text-destructive"> · not accessible</span>}
        </div>
      </div>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="destructive" size="sm"><Trash2 /></Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this library?</AlertDialogTitle>
            <AlertDialogDescription>Its videos and progress will be deleted.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction className={DESTRUCTIVE} onClick={() => void doRemove()}>Remove</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function BrowseDialog({ onSelect, onAdd }: { onSelect: (p: string) => void; onAdd: (p: string) => void }) {
  const [open, setOpen] = useState(false);
  const [bdata, setBdata] = useState<BrowseResult | null>(null);

  const go = async (p: string) => {
    try {
      setBdata(await browse(p));
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (o) void go(bdata?.path ?? "/"); }}>
      <DialogTrigger asChild><Button variant="outline"><Folder /> Browse…</Button></DialogTrigger>
      <DialogContent className="max-w-xl">
        <DialogHeader><DialogTitle>Browse folders</DialogTitle></DialogHeader>
        {bdata && (
          <>
            <div className="truncate text-sm text-muted-foreground">{bdata.path}</div>
            <div className="max-h-72 divide-y overflow-y-auto rounded-md border">
              {bdata.parent && (
                <button className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-accent"
                  onClick={() => void go(bdata.parent!)}>
                  <FolderUp className="size-4" /> ..
                </button>
              )}
              {bdata.dirs.map((d) => (
                <div key={d.path} className="flex items-center justify-between gap-2 px-3 py-2 text-sm hover:bg-accent">
                  <button className="flex min-w-0 items-center gap-2" onClick={() => void go(d.path)}>
                    <Folder className="size-4 shrink-0" /> <span className="truncate">{d.name}</span>
                  </button>
                  <Button size="sm" variant="ghost"
                    onClick={() => { onSelect(d.path); setOpen(false); }}>Select</Button>
                </div>
              ))}
              {bdata.dirs.length === 0 && (
                <div className="px-3 py-2 text-sm text-muted-foreground">(no subfolders)</div>
              )}
            </div>
            <DialogFooter>
              <Button onClick={() => { onAdd(bdata.path); setOpen(false); }}>Add this folder</Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
