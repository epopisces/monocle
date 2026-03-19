import { useEffect, useState } from 'react'
import type { Note } from '../../api/notes'
import './FormEditor.css'

// ── Template schema types ─────────────────────────────────────────

export interface TemplateField {
  name: string
  type: 'string' | 'list' | 'boolean' | 'number'
  required?: boolean
  description?: string
  default?: unknown
}

export interface TemplateSchema {
  template: string
  note_type?: string
  description?: string
  fields?: TemplateField[]
}

// ── Toast ─────────────────────────────────────────────────────────

interface ToastProps {
  message: string
  onDismiss: () => void
}

export function InlineToast({ message, onDismiss }: ToastProps) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 4000)
    return () => clearTimeout(t)
  }, [onDismiss])

  return (
    <div className="form-editor__toast" role="alert" data-testid="form-toast">
      <span>{message}</span>
      <button className="form-editor__toast-close" onClick={onDismiss} aria-label="Dismiss">✕</button>
    </div>
  )
}

// ── Field renderers ───────────────────────────────────────────────

interface FieldProps {
  field: TemplateField
  value: unknown
  onChange: (v: unknown) => void
  error?: boolean
}

function StringField({ field, value, onChange, error }: FieldProps) {
  return (
    <input
      type="text"
      className={`form-editor__input${error ? ' form-editor__input--error' : ''}`}
      value={String(value ?? '')}
      onChange={e => onChange(e.target.value)}
      placeholder={field.description ?? field.name}
      aria-label={field.name}
      data-testid={`field-${field.name}`}
    />
  )
}

function ListField({ field, value, onChange }: FieldProps) {
  // Represent list as comma-separated string for editing
  const listVal = Array.isArray(value) ? (value as string[]).join(', ') : String(value ?? '')
  return (
    <input
      type="text"
      className="form-editor__input"
      value={listVal}
      onChange={e => {
        const items = e.target.value.split(',').map(s => s.trim()).filter(Boolean)
        onChange(items)
      }}
      placeholder={`Comma-separated ${field.name}`}
      aria-label={field.name}
      data-testid={`field-${field.name}`}
    />
  )
}

function BoolField({ field, value, onChange }: FieldProps) {
  return (
    <label className="form-editor__toggle">
      <input
        type="checkbox"
        checked={Boolean(value)}
        onChange={e => onChange(e.target.checked)}
        data-testid={`field-${field.name}`}
      />
      <span className="form-editor__toggle-label">{field.description ?? field.name}</span>
    </label>
  )
}

// ── Main FormEditor component ─────────────────────────────────────

interface FormEditorProps {
  note: Note
  templates: TemplateSchema[]
  onChange: (updated: Note) => void
  onSave: () => void
}

export default function FormEditor({ note, templates, onChange, onSave }: FormEditorProps) {
  const [errors, setErrors] = useState<Set<string>>(new Set())
  const [toast, setToast] = useState<string | null>(null)

  // Find matching template
  const noteType = note.metadata?.type ?? 'other'
  const template = templates.find(
    t => t.note_type === noteType || t.template === noteType || t.template === note.metadata?.template,
  )
  const fields: TemplateField[] = template?.fields ?? []

  function fieldValue(fieldName: string): unknown {
    if (fieldName === 'title') return note.title
    const meta = note.metadata as Record<string, unknown> | undefined
    return meta?.[fieldName]
  }

  function handleFieldChange(fieldName: string, value: unknown) {
    if (fieldName === 'title') {
      onChange({ ...note, title: String(value) })
    } else {
      onChange({
        ...note,
        metadata: { ...note.metadata, [fieldName]: value } as typeof note.metadata,
      })
    }
    // Clear error for this field on change
    if (errors.has(fieldName)) {
      setErrors(prev => {
        const next = new Set(prev)
        next.delete(fieldName)
        return next
      })
    }
  }

  function handleSave() {
    // Validate required fields
    const newErrors = new Set<string>()
    for (const field of fields) {
      if (!field.required) continue
      const val = fieldValue(field.name)
      const isEmpty =
        val === null ||
        val === undefined ||
        (typeof val === 'string' && val.trim() === '') ||
        (Array.isArray(val) && val.length === 0)
      if (isEmpty) newErrors.add(field.name)
    }
    if (newErrors.size > 0) {
      setErrors(newErrors)
      const names = [...newErrors].join(', ')
      setToast(`Required fields missing: ${names}`)
      return
    }
    onSave()
  }

  // If no template, show a minimal form with just title + body
  if (fields.length === 0) {
    return (
      <div className="form-editor" data-testid="form-editor">
        {toast && <InlineToast message={toast} onDismiss={() => setToast(null)} />}
        <p className="form-editor__no-template">
          No template definition for type <strong>{noteType}</strong>. Using YAML mode to edit frontmatter fields directly.
        </p>
        <div className="form-editor__field">
          <label className="form-editor__label">Title</label>
          <input
            type="text"
            className="form-editor__input"
            value={note.title}
            onChange={e => onChange({ ...note, title: e.target.value })}
            data-testid="field-title"
          />
        </div>
        <button className="form-editor__save-btn" onClick={handleSave} data-testid="form-save-btn">
          Save
        </button>
      </div>
    )
  }

  return (
    <div className="form-editor" data-testid="form-editor">
      {toast && <InlineToast message={toast} onDismiss={() => setToast(null)} />}
      {template?.description && (
        <p className="form-editor__description">{template.description}</p>
      )}
      {fields.map(field => {
        const hasError = errors.has(field.name)
        const val = fieldValue(field.name)
        return (
          <div
            key={field.name}
            className={`form-editor__field${hasError ? ' form-editor__field--error' : ''}`}
          >
            <label className="form-editor__label">
              {field.name}
              {field.required && <span className="form-editor__required" aria-label="required"> *</span>}
            </label>
            {field.description && (
              <span className="form-editor__field-desc">{field.description}</span>
            )}
            {field.type === 'boolean' ? (
              <BoolField
                field={field}
                value={val}
                onChange={v => handleFieldChange(field.name, v)}
                error={hasError}
              />
            ) : field.type === 'list' ? (
              <ListField
                field={field}
                value={val}
                onChange={v => handleFieldChange(field.name, v)}
                error={hasError}
              />
            ) : (
              <StringField
                field={field}
                value={val}
                onChange={v => handleFieldChange(field.name, v)}
                error={hasError}
              />
            )}
            {hasError && (
              <span className="form-editor__field-error" role="alert">
                This field is required
              </span>
            )}
          </div>
        )
      })}
      <button
        className="form-editor__save-btn"
        onClick={handleSave}
        data-testid="form-save-btn"
      >
        Save
      </button>
    </div>
  )
}
