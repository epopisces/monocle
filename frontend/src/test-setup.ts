import '@testing-library/jest-dom'

// ResizeObserver is not implemented in jsdom — provide a no-op stub
window.ResizeObserver = class implements ResizeObserver {
  constructor(_callback: ResizeObserverCallback) {}
  observe(_target: Element, _options?: ResizeObserverOptions) {}
  unobserve(_target: Element) {}
  disconnect() {}
}
