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
  /** Ctrl+, / Cmd+, — open settings */
  onOpenSettings?: () => void
  /** Ctrl+\ / Cmd+\ — toggle sidebar */
  onToggleSidebar?: () => void
  /** Escape — close active modal or slide-over */
  onCloseModal?: () => void
  /** Ctrl+S / Cmd+S — save note (document editor context) */
  onSaveNote?: () => void
}

/** Returns true when the event target is an editable element where the shortcut should NOT fire */
function inEditableContext(e: KeyboardEvent): boolean {
  const target = e.target
  if (!target || !(target instanceof HTMLElement)) {
    return false
  }

  const tag = target.tagName

  // Native form inputs
  if (tag === 'INPUT' || tag === 'TEXTAREA') {
    return true
  }

  // CodeMirror and other contenteditable elements
  // isContentEditable walks up the DOM tree, so it catches both
  // the element itself and any contenteditable parent
  if (target.isContentEditable) {
    return true
  }

  // Accessible text inputs (e.g., role="textbox")
  if (target.getAttribute('role') === 'textbox') {
    return true
  }

  return false
}

export function useHotkeys(handlers: HotkeyHandlers): void {
  // Extract handler callbacks to stable references for deps array
  const {
    onSearch,
    onKeywordSearch,
    onNewNote,
    onCommandPalette,
    onOpenSettings,
    onToggleSidebar,
    onCloseModal,
    onSaveNote,
  } = handlers

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      const ctrl = e.ctrlKey || e.metaKey

      // ── Ctrl+/ — command palette ─────────────────────────────────────────
      if (ctrl && !e.shiftKey && e.key === '/') {
        e.preventDefault()
        onCommandPalette?.()
        return
      }

      // ── Escape — close modal ─────────────────────────────────────────────
      if (e.key === 'Escape') {
        onCloseModal?.()
        return
      }

      // ── Ctrl+, — open settings ──────────────────────────────────────────
      if (ctrl && !e.shiftKey && e.key === ',') {
        e.preventDefault()
        onOpenSettings?.()
        return
      }

      // ── Ctrl+Shift+K — keyword search ────────────────────────────────────
      if (ctrl && e.shiftKey && e.key.toLowerCase() === 'k') {
        if (!inEditableContext(e)) {
          e.preventDefault()
          onKeywordSearch?.()
        }
        return
      }

      // The remaining shortcuts should not fire when typing in an input/textarea
      // UNLESS they are Ctrl+S which is safe to intercept even in editors.
      if (ctrl && !e.shiftKey && e.key.toLowerCase() === 's') {
        if (onSaveNote) {
          e.preventDefault()
          onSaveNote()
        }
        return
      }

      // Skip remaining Ctrl shortcuts when focused on editable elements
      if (inEditableContext(e)) return

      if (ctrl && !e.shiftKey) {
        switch (e.key.toLowerCase()) {
          case 'k':
            e.preventDefault()
            onSearch?.()
            return
          case 'n':
            e.preventDefault()
            onNewNote?.()
            return
          case '\\':
            e.preventDefault()
            onToggleSidebar?.()
            return
        }
      }
    },
    [onSearch, onKeywordSearch, onNewNote, onCommandPalette, onOpenSettings, onToggleSidebar, onCloseModal, onSaveNote],
  )

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])
}
