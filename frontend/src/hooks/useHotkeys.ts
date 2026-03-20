/**
 * useHotkeys — application-wide keyboard shortcut registration
 *
 * Supports Ctrl (Windows/Linux) and Cmd (macOS) equivalents for each shortcut.
 *
 * Usage:
 *   const { openCommandPalette, ... } = useHotkeys({
 *     onSearch, onKeywordSearch, onNewNote, onCommandPalette,
 *     onToggleSidebar, onCloseModal, onSaveNote,
 *   })
 *
 * Each handler is optional — omit the ones not relevant to the current
 * render context.
 */

import { useEffect, useCallback } from 'react'

export interface HotkeyHandlers {
  /** Ctrl+K / Cmd+K — open semantic search */
  onSearch?: () => void
  /** Ctrl+Shift+K / Cmd+Shift+K — open keyword search */
  onKeywordSearch?: () => void
  /** Ctrl+N / Cmd+N — new note (open template picker) */
  onNewNote?: () => void
  /** Ctrl+/ / Cmd+/ — open command palette */
  onCommandPalette?: () => void
  /** Ctrl+\ / Cmd+\ — toggle sidebar */
  onToggleSidebar?: () => void
  /** Escape — close active modal or slide-over */
  onCloseModal?: () => void
  /** Ctrl+S / Cmd+S — save note (document editor context) */
  onSaveNote?: () => void
}

/** Returns true when the event target is an editable element where the shortcut should NOT fire */
function inEditableContext(e: KeyboardEvent): boolean {
  const tag = (e.target as HTMLElement).tagName
  return tag === 'INPUT' || tag === 'TEXTAREA'
}

export function useHotkeys(handlers: HotkeyHandlers): void {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      const ctrl = e.ctrlKey || e.metaKey

      // ── Ctrl+/ — command palette ─────────────────────────────────────────
      if (ctrl && !e.shiftKey && e.key === '/') {
        e.preventDefault()
        handlers.onCommandPalette?.()
        return
      }

      // ── Escape — close modal ─────────────────────────────────────────────
      if (e.key === 'Escape') {
        handlers.onCloseModal?.()
        return
      }

      // ── Ctrl+Shift+K — keyword search ────────────────────────────────────
      if (ctrl && e.shiftKey && e.key.toLowerCase() === 'k') {
        if (!inEditableContext(e)) {
          e.preventDefault()
          handlers.onKeywordSearch?.()
        }
        return
      }

      // The remaining shortcuts should not fire when typing in an input/textarea
      // UNLESS they are Ctrl+S which is safe to intercept even in editors.
      if (ctrl && !e.shiftKey && e.key.toLowerCase() === 's') {
        if (handlers.onSaveNote) {
          e.preventDefault()
          handlers.onSaveNote()
        }
        return
      }

      // Skip remaining Ctrl shortcuts when focused on editable elements
      if (inEditableContext(e)) return

      if (ctrl && !e.shiftKey) {
        switch (e.key.toLowerCase()) {
          case 'k':
            e.preventDefault()
            handlers.onSearch?.()
            return
          case 'n':
            e.preventDefault()
            handlers.onNewNote?.()
            return
          case '\\':
            e.preventDefault()
            handlers.onToggleSidebar?.()
            return
        }
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [handlers],
  )

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])
}
