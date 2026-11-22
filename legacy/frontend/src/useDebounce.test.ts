/**
 * useDebouncedCallback hook — unit tests.
 *
 * Covers:
 *  - fn is not called synchronously
 *  - fn is called after the delay
 *  - rapid calls → only last fires
 *  - cancel() prevents pending invocation
 *  - cancel() allows subsequent calls
 *  - unmount clears the pending timer
 *  - multiple arguments passed through
 *  - returned callback reference is stable across re-renders
 *  - latest fn reference used without changing callback identity
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useDebouncedCallback } from './hooks/useDebounce'

describe('useDebouncedCallback', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

  it('does not call fn synchronously', () => {
    const fn = vi.fn()
    const { result } = renderHook(() => useDebouncedCallback(fn, 300))
    act(() => result.current('arg'))
    expect(fn).not.toHaveBeenCalled()
  })

  it('calls fn exactly once after the delay elapses', () => {
    const fn = vi.fn()
    const { result } = renderHook(() => useDebouncedCallback(fn, 300))
    act(() => result.current('arg'))
    act(() => vi.advanceTimersByTime(300))
    expect(fn).toHaveBeenCalledOnce()
    expect(fn).toHaveBeenCalledWith('arg')
  })

  it('does not call fn before the delay elapses', () => {
    const fn = vi.fn()
    const { result } = renderHook(() => useDebouncedCallback(fn, 300))
    act(() => result.current('arg'))
    act(() => vi.advanceTimersByTime(299))
    expect(fn).not.toHaveBeenCalled()
  })

  it('rapid calls reset the timer — only last call fires', () => {
    const fn = vi.fn()
    const { result } = renderHook(() => useDebouncedCallback(fn, 300))
    act(() => {
      result.current('call1')
      result.current('call2')
      result.current('call3')
    })
    act(() => vi.advanceTimersByTime(300))
    expect(fn).toHaveBeenCalledOnce()
    expect(fn).toHaveBeenCalledWith('call3')
  })

  it('interleaved calls — intermediate timer is cancelled', () => {
    const fn = vi.fn()
    const { result } = renderHook(() => useDebouncedCallback(fn, 200))
    act(() => result.current('first'))
    act(() => vi.advanceTimersByTime(100)) // not yet
    act(() => result.current('second'))
    act(() => vi.advanceTimersByTime(100)) // only 100ms from 'second' — still pending
    expect(fn).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(100)) // 200ms from 'second'
    expect(fn).toHaveBeenCalledOnce()
    expect(fn).toHaveBeenCalledWith('second')
  })

  it('cancel() prevents a pending invocation from firing', () => {
    const fn = vi.fn()
    const { result } = renderHook(() => useDebouncedCallback(fn, 300))
    act(() => result.current('arg'))
    act(() => result.current.cancel())
    act(() => vi.advanceTimersByTime(300))
    expect(fn).not.toHaveBeenCalled()
  })

  it('cancel() is safe to call when no timer is pending', () => {
    const fn = vi.fn()
    const { result } = renderHook(() => useDebouncedCallback(fn, 300))
    expect(() => act(() => result.current.cancel())).not.toThrow()
  })

  it('subsequent calls work normally after cancel()', () => {
    const fn = vi.fn()
    const { result } = renderHook(() => useDebouncedCallback(fn, 300))
    act(() => result.current('first'))
    act(() => result.current.cancel())
    act(() => result.current('second'))
    act(() => vi.advanceTimersByTime(300))
    expect(fn).toHaveBeenCalledOnce()
    expect(fn).toHaveBeenCalledWith('second')
  })

  it('unmount clears the pending timer so fn is not called', () => {
    const fn = vi.fn()
    const { result, unmount } = renderHook(() => useDebouncedCallback(fn, 300))
    act(() => result.current('arg'))
    unmount()
    act(() => vi.advanceTimersByTime(300))
    expect(fn).not.toHaveBeenCalled()
  })

  it('passes multiple positional arguments through to fn', () => {
    const fn = vi.fn()
    const { result } = renderHook(() => useDebouncedCallback(fn, 100))
    act(() => (result.current as (...args: unknown[]) => void)('a', 'b', 'c'))
    act(() => vi.advanceTimersByTime(100))
    expect(fn).toHaveBeenCalledWith('a', 'b', 'c')
  })

  it('returned callback reference is stable across re-renders', () => {
    const fn = vi.fn()
    const { result, rerender } = renderHook(() => useDebouncedCallback(fn, 300))
    const first = result.current
    rerender()
    rerender()
    expect(result.current).toBe(first)
  })

  it('uses the latest fn closure without changing the callback reference', () => {
    let callIndex = 0
    const fn1 = vi.fn(() => { callIndex = 1 })
    const fn2 = vi.fn(() => { callIndex = 2 })
    let currentFn = fn1

    const { result, rerender } = renderHook(() => useDebouncedCallback(currentFn, 300))
    const stableCallback = result.current

    // Update closure fn
    currentFn = fn2
    rerender()

    expect(result.current).toBe(stableCallback) // still same reference
    act(() => result.current('arg'))
    act(() => vi.advanceTimersByTime(300))
    expect(callIndex).toBe(2) // called fn2
    expect(fn1).not.toHaveBeenCalled()
  })

  it('delay change resets the pending timer', () => {
    const fn = vi.fn()
    let delay = 300
    const { result, rerender } = renderHook(() => useDebouncedCallback(fn, delay))
    act(() => result.current('arg'))
    // Change delay to 100 — a new callback is returned
    delay = 100
    rerender()
    // Old timer from delay=300 should have been superseded
    act(() => vi.advanceTimersByTime(100))
    // No call should happen yet since the new callback hasn't been invoked
    expect(fn).not.toHaveBeenCalled()
    // Invoke new callback and wait for new delay
    act(() => result.current('arg2'))
    act(() => vi.advanceTimersByTime(100))
    expect(fn).toHaveBeenCalledOnce()
    expect(fn).toHaveBeenCalledWith('arg2')
  })
})
