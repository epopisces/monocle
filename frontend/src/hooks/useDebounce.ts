import { useCallback, useEffect, useRef } from 'react'

/**
 * Returns a debounced version of `fn` that delays invocation until `delay` ms
 * after the last call. The stable callback reference never changes — only the timer.
 */
export function useDebouncedCallback<Args extends unknown[]>(
  fn: (...args: Args) => void,
  delay: number,
): (...args: Args) => void {
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const fnRef = useRef(fn)

  // Keep fnRef fresh without invalidating the returned callback.
  useEffect(() => {
    fnRef.current = fn
  })

  return useCallback(
    (...args: Args) => {
      clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => fnRef.current(...args), delay)
    },
    [delay],
  )
}
