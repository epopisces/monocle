import { useCallback, useEffect, useRef } from 'react'

export interface DebouncedCallback<Args extends unknown[]> {
  (...args: Args): void
  cancel(): void
}

/**
 * Returns a debounced version of `fn` that delays invocation until `delay` ms
 * after the last call. The stable callback reference never changes — only the timer.
 * 
 * The returned callback includes a `cancel()` method to explicitly clear any pending invocation.
 * A cleanup effect automatically clears the pending timeout on unmount.
 */
export function useDebouncedCallback<Args extends unknown[]>(
  fn: (...args: Args) => void,
  delay: number,
): DebouncedCallback<Args> {
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const fnRef = useRef(fn)

  // Keep fnRef fresh without invalidating the returned callback.
  useEffect(() => {
    fnRef.current = fn
  })

  // Clean up pending timeout on unmount to prevent stale callbacks.
  useEffect(() => {
    return () => {
      if (timerRef.current !== undefined) {
        clearTimeout(timerRef.current)
        timerRef.current = undefined
      }
    }
  }, [])

  const debounced = useCallback(
    (...args: Args) => {
      clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => fnRef.current(...args), delay)
    },
    [delay],
  ) as DebouncedCallback<Args>

  // Attach cancel method for explicit cancellation (e.g., on navigation).
  debounced.cancel = useCallback(() => {
    if (timerRef.current !== undefined) {
      clearTimeout(timerRef.current)
      timerRef.current = undefined
    }
  }, [])

  return debounced
}
