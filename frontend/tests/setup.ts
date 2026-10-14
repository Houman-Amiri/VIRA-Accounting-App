import "@/lib/i18n";
import "@testing-library/jest-dom/vitest";

// jsdom lacks ResizeObserver (react-zoom-pan-pinch needs it).
class _ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
(globalThis as { ResizeObserver?: unknown }).ResizeObserver ??= _ResizeObserverStub;
