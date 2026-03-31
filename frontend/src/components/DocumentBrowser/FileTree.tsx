import { useCallback, useEffect, useRef, useState } from 'react'
import type { NoteRef } from '../../api/notes'
import { patchNote, deleteNote } from '../../api/notes'
import './FileTree.css'

// ── Tree data structure ───────────────────────────────────────────

interface FolderNode {
  kind: 'folder'
  name: string
  path: string
  children: TreeNode[]
}
interface FileNode {
  kind: 'file'
  name: string
  path: string
  note: NoteRef
}
type TreeNode = FolderNode | FileNode

function buildTree(notes: NoteRef[]): TreeNode[] {
  const root: TreeNode[] = []
  for (const note of notes) {
    const parts = note.file_path.replace(/\\/g, '/').split('/')
    let current: TreeNode[] = root
    for (let i = 0; i < parts.length - 1; i++) {
      const name = parts[i]
      const path = parts.slice(0, i + 1).join('/')
      let folder = current.find(
        (n): n is FolderNode => n.kind === 'folder' && n.name === name,
      )
      if (!folder) {
        folder = { kind: 'folder', name, path, children: [] }
        current.push(folder)
      }
      current = folder.children
    }
    const fileName = parts[parts.length - 1]
    current.push({ kind: 'file', name: fileName, path: note.file_path, note })
  }
  return root
}

// ── Type icons ────────────────────────────────────────────────────

const TYPE_ICONS: Record<string, string> = {
  person_note: '👤',
  decision: '⚡',
  idea: '💡',
  observation: '👁',
  reference: '🔗',
  meeting_note: '📅',
  project: '📁',
  action_item: '✅',
  weekly_summary: '📊',
  other: '📄',
}

function fileIcon(note: NoteRef): string {
  return TYPE_ICONS[note.type] ?? '📄'
}

// ── Tree actions (passed down from FileTree) ──────────────────────

interface TreeActions {
  onContextMenu: (node: FileNode, e: React.MouseEvent) => void
  renamingPath: string | null
  renameValue: string
  renameLoading: boolean
  renameError: string | null
  onRenameChange: (v: string) => void
  onRenameCommit: () => void
  onRenameCancel: () => void
  deletingPath: string | null
  deleteLoading: boolean
  onDeleteConfirm: () => void
  onDeleteCancel: () => void
}

// ── Tree node renderer ────────────────────────────────────────────

interface TreeNodeProps {
  node: TreeNode
  selectedPath: string | null
  onSelect: (path: string) => void
  depth: number
  actions: TreeActions
}

function TreeNodeRow({ node, selectedPath, onSelect, depth, actions }: TreeNodeProps) {
  const [open, setOpen] = useState(depth === 0)

  if (node.kind === 'folder') {
    return (
      <div className="file-tree__folder" data-testid="tree-folder">
        <button
          className="file-tree__folder-row"
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
          onClick={() => setOpen(o => !o)}
          aria-expanded={open}
        >
          <span className="file-tree__arrow">{open ? '▾' : '▸'}</span>
          <span className="file-tree__folder-icon">📂</span>
          <span className="file-tree__folder-name">{node.name}</span>
        </button>
        {open && (
          <div className="file-tree__children">
            {node.children.map(child => (
              <TreeNodeRow
                key={child.path}
                node={child}
                selectedPath={selectedPath}
                onSelect={onSelect}
                depth={depth + 1}
                actions={actions}
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  // File node
  const isSelected = node.path === selectedPath
  const pendingReview = node.note.review_status === 'pending'
  const isRenaming = actions.renamingPath === node.path
  const isDeleting = actions.deletingPath === node.path

  if (isRenaming) {
    return (
      <div
        className={`file-tree__file file-tree__file--renaming${isSelected ? ' file-tree__file--active' : ''}`}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        data-testid="tree-file-renaming"
      >
        <span className="file-tree__file-icon">{fileIcon(node.note)}</span>
        <input
          className="file-tree__rename-input"
          value={actions.renameValue}
          onChange={e => actions.onRenameChange(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') { e.preventDefault(); actions.onRenameCommit() }
            if (e.key === 'Escape') { e.preventDefault(); actions.onRenameCancel() }
          }}
          onBlur={actions.onRenameCancel}
          autoFocus
          disabled={actions.renameLoading}
          data-testid="rename-input"
        />
        {actions.renameError && (
          <span className="file-tree__rename-error" title={actions.renameError}>!</span>
        )}
      </div>
    )
  }

  if (isDeleting) {
    return (
      <div
        className={`file-tree__file file-tree__file--deleting${isSelected ? ' file-tree__file--active' : ''}`}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        data-testid="tree-file-deleting"
      >
        <span className="file-tree__delete-label">Delete?</span>
        <button
          className="file-tree__delete-confirm-btn"
          onClick={actions.onDeleteConfirm}
          disabled={actions.deleteLoading}
          data-testid="delete-confirm-btn"
        >
          {actions.deleteLoading ? '…' : 'Yes'}
        </button>
        <button
          className="file-tree__delete-cancel-btn"
          onClick={actions.onDeleteCancel}
          disabled={actions.deleteLoading}
          data-testid="delete-cancel-btn"
        >
          No
        </button>
      </div>
    )
  }

  return (
    <button
      className={`file-tree__file${isSelected ? ' file-tree__file--active' : ''}`}
      style={{ paddingLeft: `${depth * 12 + 8}px` }}
      onClick={() => onSelect(node.path)}
      onContextMenu={e => actions.onContextMenu(node, e)}
      data-testid="tree-file"
      aria-current={isSelected ? 'page' : undefined}
      title={node.path}
    >
      <span className="file-tree__file-icon">{fileIcon(node.note)}</span>
      <span className="file-tree__file-name">
        {node.note.title || node.name}
      </span>
      {pendingReview && (
        <span className="file-tree__pending-badge" title="Pending review" aria-label="pending review">●</span>
      )}
    </button>
  )
}

// ── Public component ──────────────────────────────────────────────

interface FileTreeProps {
  notes: NoteRef[]
  selectedPath: string | null
  onSelect: (path: string) => void
  onDeleted?: (path: string) => void
  onRenamed?: (path: string, newTitle: string) => void
}

export default function FileTree({ notes, selectedPath, onSelect, onDeleted, onRenamed }: FileTreeProps) {
  const tree = buildTree(notes)

  // Context menu state
  const [menuState, setMenuState] = useState<{ node: FileNode; x: number; y: number } | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  // Rename state
  const [renamingPath, setRenamingPath] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [renameLoading, setRenameLoading] = useState(false)
  const [renameError, setRenameError] = useState<string | null>(null)
  const renameCommittingRef = useRef(false)

  // Delete state
  const [deletingPath, setDeletingPath] = useState<string | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)

  // Close context menu on outside click or Escape
  useEffect(() => {
    if (!menuState) return
    const onMouseDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuState(null)
      }
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuState(null) }
    document.addEventListener('mousedown', onMouseDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onMouseDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [menuState])

  const handleContextMenu = useCallback((node: FileNode, e: React.MouseEvent) => {
    e.preventDefault()
    const x = Math.min(e.clientX, window.innerWidth - 168)
    const y = Math.min(e.clientY, window.innerHeight - 120)
    setMenuState({ node, x, y })
  }, [])

  const handleMenuEdit = useCallback(() => {
    if (!menuState) return
    onSelect(menuState.node.path)
    setMenuState(null)
  }, [menuState, onSelect])

  const handleMenuRename = useCallback(() => {
    if (!menuState) return
    const current = menuState.node.note.title || menuState.node.name.replace(/\.md$/, '')
    setRenamingPath(menuState.node.path)
    setRenameValue(current)
    setRenameError(null)
    renameCommittingRef.current = false
    setMenuState(null)
  }, [menuState])

  const handleMenuDelete = useCallback(() => {
    if (!menuState) return
    setDeletingPath(menuState.node.path)
    setMenuState(null)
  }, [menuState])

  const handleRenameCommit = useCallback(async () => {
    if (!renamingPath || renameLoading || renameCommittingRef.current) return
    renameCommittingRef.current = true
    const newTitle = renameValue.trim()
    if (!newTitle) {
      setRenamingPath(null)
      renameCommittingRef.current = false
      return
    }
    setRenameLoading(true)
    setRenameError(null)
    try {
      await patchNote(renamingPath, { updates: { title: newTitle } })
      onRenamed?.(renamingPath, newTitle)
      setRenamingPath(null)
    } catch (e) {
      setRenameError(String((e as Error)?.message ?? 'Rename failed'))
      renameCommittingRef.current = false
    } finally {
      setRenameLoading(false)
    }
  }, [renamingPath, renameValue, renameLoading, onRenamed])

  const handleRenameCancel = useCallback(() => {
    if (renameCommittingRef.current) return
    setRenamingPath(null)
    setRenameError(null)
  }, [])

  const handleDeleteConfirm = useCallback(async () => {
    if (!deletingPath || deleteLoading) return
    setDeleteLoading(true)
    try {
      await deleteNote(deletingPath)
      const deleted = deletingPath
      setDeletingPath(null)
      onDeleted?.(deleted)
    } catch {
      setDeletingPath(null)
    } finally {
      setDeleteLoading(false)
    }
  }, [deletingPath, deleteLoading, onDeleted])

  const handleDeleteCancel = useCallback(() => {
    setDeletingPath(null)
  }, [])

  const actions: TreeActions = {
    onContextMenu: handleContextMenu,
    renamingPath,
    renameValue,
    renameLoading,
    renameError,
    onRenameChange: setRenameValue,
    onRenameCommit: handleRenameCommit,
    onRenameCancel: handleRenameCancel,
    deletingPath,
    deleteLoading,
    onDeleteConfirm: handleDeleteConfirm,
    onDeleteCancel: handleDeleteCancel,
  }

  if (notes.length === 0) {
    return (
      <div className="file-tree file-tree--empty" data-testid="file-tree">
        <span className="file-tree__empty-msg">No notes found</span>
      </div>
    )
  }

  return (
    <>
      <nav className="file-tree" data-testid="file-tree" aria-label="Vault file tree">
        {tree.map(node => (
          <TreeNodeRow
            key={node.path}
            node={node}
            selectedPath={selectedPath}
            onSelect={onSelect}
            depth={0}
            actions={actions}
          />
        ))}
      </nav>

      {menuState && (
        <div
          className="file-tree__context-menu"
          style={{ top: menuState.y, left: menuState.x }}
          ref={menuRef}
          data-testid="context-menu"
          role="menu"
        >
          <button
            className="file-tree__context-item"
            onClick={handleMenuEdit}
            role="menuitem"
            data-testid="context-edit"
          >
            ✎ Edit
          </button>
          <button
            className="file-tree__context-item"
            onClick={handleMenuRename}
            role="menuitem"
            data-testid="context-rename"
          >
            ✏ Rename
          </button>
          <button
            className="file-tree__context-item file-tree__context-item--danger"
            onClick={handleMenuDelete}
            role="menuitem"
            data-testid="context-delete"
          >
            🗑 Delete
          </button>
        </div>
      )}
    </>
  )
}
