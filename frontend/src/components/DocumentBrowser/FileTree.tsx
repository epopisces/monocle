import { useState } from 'react'
import type { NoteRef } from '../../api/notes'
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

// ── Tree node renderer ────────────────────────────────────────────

interface TreeNodeProps {
  node: TreeNode
  selectedPath: string | null
  onSelect: (path: string) => void
  depth: number
}

function TreeNodeRow({ node, selectedPath, onSelect, depth }: TreeNodeProps) {
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
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  const isSelected = node.path === selectedPath
  const pendingReview = node.note.review_status === 'pending'

  return (
    <button
      className={`file-tree__file${isSelected ? ' file-tree__file--active' : ''}`}
      style={{ paddingLeft: `${depth * 12 + 8}px` }}
      onClick={() => onSelect(node.path)}
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
}

export default function FileTree({ notes, selectedPath, onSelect }: FileTreeProps) {
  const tree = buildTree(notes)

  if (notes.length === 0) {
    return (
      <div className="file-tree file-tree--empty" data-testid="file-tree">
        <span className="file-tree__empty-msg">No notes found</span>
      </div>
    )
  }

  return (
    <nav className="file-tree" data-testid="file-tree" aria-label="Vault file tree">
      {tree.map(node => (
        <TreeNodeRow
          key={node.path}
          node={node}
          selectedPath={selectedPath}
          onSelect={onSelect}
          depth={0}
        />
      ))}
    </nav>
  )
}
