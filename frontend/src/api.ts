// Typed API client. Grows alongside the backend.

const BASE = "/api";

export interface Health {
  status: string;
  service: string;
  version: string;
}

export interface CourseCard {
  id: number;
  slug: string;
  title: string;
  category: string | null;
  provider: string | null;
  library: string | null;
  cover: string | null;
  previews: string[];
  lectureCount: number;
  completedCount: number;
  lastActivity: string | null;
  createdAt: string | null;
}

export interface LibraryResponse {
  courses: CourseCard[];
  categories: string[];
  providers: string[];
  libraries: string[];
}

export type Playback = "native" | "mpegts" | "remux" | "document";

export interface LectureItem {
  id: number;
  title: string;
  kind: string;
  playback: Playback;
  needsTranscode: boolean;
  hasSubtitle: boolean;
  durationSec: number | null;
  positionSec: number;
  completed: boolean;
  stream: string;
  subtitle: string | null;
}

export interface AudioTrack {
  index: number;
  language: string | null;
  title: string | null;
  channels: number | null;
}

export const getAudioTracks = (lectureId: number) =>
  getJSON<AudioTrack[]>(`/lectures/${lectureId}/audio-tracks`);

export interface SectionItem {
  id: number;
  title: string;
  lectures: LectureItem[];
}

export interface CourseDetail {
  slug: string;
  title: string;
  category: string | null;
  provider: string | null;
  cover: string | null;
  lectureCount: number;
  completedCount: number;
  resumeLectureId: number | null;
  sections: SectionItem[];
  attachments: { id: number; title: string; kind: string }[];
}

export interface ProgressIn {
  position_sec: number;
  duration_sec?: number | null;
  completed?: boolean;
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorized = fn;
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { credentials: "include" });
  if (res.status === 401) {
    onUnauthorized?.();
    throw new Error("unauthorized");
  }
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export interface Me {
  username: string;
  isAdmin: boolean;
  authDisabled: boolean;
}

export interface UserRow {
  id: number;
  username: string;
  isAdmin: boolean;
  allLibraries: boolean;
  libraryIds: number[];
}

export async function getMe(): Promise<Me | null> {
  const res = await fetch(`${BASE}/auth/me`, { credentials: "include" });
  if (res.status === 401) return null;
  if (!res.ok) throw new Error(`me -> ${res.status}`);
  return res.json();
}

export interface AuthStatus {
  authDisabled: boolean;
  needsSetup: boolean;
  user: { username: string; isAdmin: boolean } | null;
}

export async function getStatus(): Promise<AuthStatus> {
  const res = await fetch(`${BASE}/auth/status`, { credentials: "include" });
  if (!res.ok) throw new Error(`status -> ${res.status}`);
  return res.json();
}

export async function setupAdmin(username: string, password: string): Promise<void> {
  const res = await fetch(`${BASE}/auth/setup`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d?.detail || "setup failed");
  }
}

export async function login(username: string, password: string): Promise<Me> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error("Invalid username or password");
  return res.json();
}

export async function logout(): Promise<void> {
  await fetch(`${BASE}/auth/logout`, { method: "POST", credentials: "include" });
}

async function postJSON(path: string, body: unknown): Promise<void> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d?.detail || `request failed (${res.status})`);
  }
}

export const getUsers = () => getJSON<UserRow[]>("/users");
export const createUser = (username: string, password: string, isAdmin: boolean) =>
  postJSON("/users", { username, password, is_admin: isAdmin });
export const resetUserPassword = (id: number, password: string) =>
  postJSON(`/users/${id}/password`, { password });
export const changeMyPassword = (current_password: string, new_password: string) =>
  postJSON("/auth/password", { current_password, new_password });

export async function setUserAccess(
  id: number,
  allLibraries: boolean,
  libraryIds: number[],
): Promise<void> {
  const res = await fetch(`${BASE}/users/${id}/access`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ all_libraries: allLibraries, library_ids: libraryIds }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d?.detail || `access failed (${res.status})`);
  }
}

export async function deleteUser(id: number): Promise<void> {
  const res = await fetch(`${BASE}/users/${id}`, { method: "DELETE", credentials: "include" });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d?.detail || `delete failed (${res.status})`);
  }
}

export interface SearchResult {
  kind: "course" | "lecture";
  refId: number;
  slug: string;
  title: string;
  context: string;
}

export const getHealth = () => getJSON<Health>("/health");
export const getCourses = () => getJSON<LibraryResponse>("/courses");
export const getCourse = (slug: string) =>
  getJSON<CourseDetail>(`/courses/${encodeURIComponent(slug)}`);
export const getSearch = (q: string) =>
  getJSON<{ results: SearchResult[] }>(`/search?q=${encodeURIComponent(q)}`);

export interface LibraryItem {
  id: number;
  path: string;
  name: string | null;
  courseCount: number;
  accessible: boolean;
}

export interface BrowseResult {
  path: string;
  parent: string | null;
  dirs: { name: string; path: string }[];
}

export const getLibraries = () => getJSON<LibraryItem[]>("/libraries");
export const browse = (path: string) =>
  getJSON<BrowseResult>(`/libraries/browse?path=${encodeURIComponent(path)}`);

export async function addLibrary(path: string, name?: string): Promise<void> {
  const res = await fetch(`${BASE}/libraries`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, name }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail?.detail || `add failed (${res.status})`);
  }
}

export async function deleteLibrary(id: number): Promise<void> {
  const res = await fetch(`${BASE}/libraries/${id}`, { method: "DELETE", credentials: "include" });
  if (!res.ok) throw new Error(`delete failed (${res.status})`);
}

export async function rescanAll(): Promise<void> {
  await fetch(`${BASE}/admin/rescan`, { method: "POST", credentials: "include" });
}

export interface ScanStatus {
  running: boolean;
  phase: string;
  librariesTotal: number;
  librariesDone: number;
  current: string | null;
  courses: number;
  lectures: number;
  errors: { library: string; error: string }[];
  finished: number | null;
}

export const getScanStatus = () => getJSON<ScanStatus>("/admin/scan-status");

export interface BdmvTitle {
  id: string;
  label: string;
  durationSec: number;
  segments: number;
  converted: boolean;
}

export interface BdmvDisc {
  path: string;
  name: string;
  titles: BdmvTitle[];
}

export interface BdmvDiscs {
  discs: BdmvDisc[];
  count: number;
  pending: number;
  converted: number;
}

export interface BdmvStatus {
  running: boolean;
  phase: string;
  current: string | null;
  done: number;
  total: number;
  percent: number;
  errors: { disc: string; title?: string; error: string }[];
  finished: number | null;
}

export const getBdmvDiscs = () => getJSON<BdmvDiscs>("/admin/bdmv");
export const getBdmvStatus = () => getJSON<BdmvStatus>("/admin/bdmv/status");
export async function startBdmvConvert(titles?: string[]): Promise<void> {
  await fetch(`${BASE}/admin/bdmv/convert`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ titles: titles ?? null }),
  });
}
export async function deleteBdmvTitles(titles: string[]): Promise<void> {
  await fetch(`${BASE}/admin/bdmv/delete`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ titles }),
  });
}

export async function putProgress(lectureId: number, body: ProgressIn): Promise<void> {
  await fetch(`${BASE}/progress/${lectureId}`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function resetCourseProgress(slug: string): Promise<void> {
  const res = await fetch(`${BASE}/progress/course/${encodeURIComponent(slug)}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) throw new Error(`reset failed (${res.status})`);
}

export async function completeCourse(slug: string): Promise<void> {
  const res = await fetch(`${BASE}/progress/course/${encodeURIComponent(slug)}/complete`, {
    method: "PUT",
    credentials: "include",
  });
  if (!res.ok) throw new Error(`complete failed (${res.status})`);
}

export interface NoteItem {
  id: number;
  positionSec: number;
  text: string;
}

export const getNotes = (lectureId: number) =>
  getJSON<NoteItem[]>(`/notes?lecture=${lectureId}`);

export async function createNote(lectureId: number, positionSec: number, text: string): Promise<void> {
  await fetch(`${BASE}/notes`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lecture_id: lectureId, position_sec: positionSec, text }),
  });
}

export async function deleteNote(id: number): Promise<void> {
  await fetch(`${BASE}/notes/${id}`, { method: "DELETE", credentials: "include" });
}
