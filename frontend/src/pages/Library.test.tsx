import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CourseCard, LibraryResponse } from "@/api";

// AppHeader pulls in auth/query wiring we don't care about here — stub it but
// keep rendering the search box it's handed so search still works.
vi.mock("@/components/AppHeader", () => ({
  default: ({ center }: { center?: ReactNode }) => <div data-testid="hdr">{center}</div>,
}));

const getCourses = vi.fn<[], Promise<LibraryResponse>>();
const getSearch = vi.fn();
const resetCourseProgress = vi.fn<[string], Promise<void>>();
const completeCourse = vi.fn<[string], Promise<void>>();
vi.mock("@/api", () => ({
  getCourses: () => getCourses(),
  getSearch: (q: string) => getSearch(q),
  resetCourseProgress: (slug: string) => resetCourseProgress(slug),
  completeCourse: (slug: string) => completeCourse(slug),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import Library from "@/pages/Library";

function card(over: Partial<CourseCard>): CourseCard {
  return {
    id: Math.floor(Math.random() * 1e9),
    slug: `s-${Math.random()}`,
    title: "Untitled",
    category: null,
    provider: null,
    cover: null,
    previews: [],
    lectureCount: 5,
    completedCount: 0,
    lastActivity: null,
    createdAt: null,
    ...over,
  };
}

function renderLibrary() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Library />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getCourses.mockReset();
  getSearch.mockReset();
  resetCourseProgress.mockReset().mockResolvedValue();
  completeCourse.mockReset().mockResolvedValue();
  getSearch.mockResolvedValue({ results: [] });
});

describe("Library page", () => {
  it("renders courses returned by the API", async () => {
    getCourses.mockResolvedValue({
      courses: [card({ title: "Unreal Engine 5" }), card({ title: "Blender Basics" })],
      categories: [],
    });
    renderLibrary();
    expect(await screen.findByText("Unreal Engine 5")).toBeInTheDocument();
    expect(screen.getByText("Blender Basics")).toBeInTheDocument();
  });

  it("shows the empty state when there are no courses", async () => {
    getCourses.mockResolvedValue({ courses: [], categories: [] });
    renderLibrary();
    expect(await screen.findByText("No videos yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /add a library/i })).toBeInTheDocument();
  });

  it("filters by category chip", async () => {
    getCourses.mockResolvedValue({
      courses: [
        card({ title: "Udemy Course", category: "Udemy" }),
        card({ title: "Skillshare Course", category: "Skillshare" }),
      ],
      categories: ["Udemy", "Skillshare"],
    });
    renderLibrary();
    await screen.findByText("Udemy Course");

    await userEvent.click(screen.getByRole("button", { name: "Skillshare" }));

    expect(screen.queryByText("Udemy Course")).not.toBeInTheDocument();
    expect(screen.getByText("Skillshare Course")).toBeInTheDocument();
  });

  it("filters by provider independently of topic", async () => {
    getCourses.mockResolvedValue({
      courses: [
        card({ title: "Blender (Udemy)", provider: "Udemy", category: "3D Art" }),
        card({ title: "ZBrush (Gumroad)", provider: "Gumroad", category: "3D Art" }),
      ],
      categories: ["3D Art"],
      providers: ["Udemy", "Gumroad"],
    });
    renderLibrary();
    await screen.findByText("Blender (Udemy)");

    const providerSelect = screen.getAllByRole("combobox")[0];
    await userEvent.selectOptions(providerSelect, "Gumroad");

    await waitFor(() => expect(screen.queryByText("Blender (Udemy)")).not.toBeInTheDocument());
    expect(screen.getByText("ZBrush (Gumroad)")).toBeInTheDocument();
  });

  it("resets a course's progress from the options menu (with confirmation)", async () => {
    getCourses.mockResolvedValue({
      courses: [card({ slug: "ue5", title: "Unreal Engine 5", completedCount: 2 })],
      categories: [],
    });
    renderLibrary();
    await screen.findByText("Unreal Engine 5");

    await userEvent.click(screen.getByRole("button", { name: /^options$/i }));
    await userEvent.click(await screen.findByText("Reset progress"));

    // confirm dialog gates the destructive action
    expect(resetCourseProgress).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /reset progress/i }));

    await waitFor(() => expect(resetCourseProgress).toHaveBeenCalledWith("ue5"));
  });

  it("marks a whole course complete from the options menu", async () => {
    getCourses.mockResolvedValue({
      courses: [card({ slug: "blender", title: "Blender Basics" })],
      categories: [],
    });
    renderLibrary();
    await screen.findByText("Blender Basics");

    await userEvent.click(screen.getByRole("button", { name: /^options$/i }));
    await userEvent.click(await screen.findByText("Mark all complete"));

    await waitFor(() => expect(completeCourse).toHaveBeenCalledWith("blender"));
  });

  it("filters by completion status", async () => {
    getCourses.mockResolvedValue({
      courses: [
        card({ title: "Done Course", lectureCount: 3, completedCount: 3 }),
        card({ title: "Fresh Course", lectureCount: 3, completedCount: 0 }),
      ],
      categories: [],
    });
    renderLibrary();
    await screen.findByText("Done Course");

    const statusSelect = screen.getAllByRole("combobox")[0];
    await userEvent.selectOptions(statusSelect, "completed");

    await waitFor(() => expect(screen.queryByText("Fresh Course")).not.toBeInTheDocument());
    expect(screen.getByText("Done Course")).toBeInTheDocument();
  });
});
