import "@testing-library/jest-dom/vitest";

import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// Radix (dropdown/alert-dialog) relies on a few DOM APIs jsdom doesn't implement.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = vi.fn(() => false);
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = vi.fn();
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn();
}
