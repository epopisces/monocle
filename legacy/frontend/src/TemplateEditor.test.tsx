import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import FormEditor from './components/DocumentBrowser/FormEditor'
import type { TemplateSchema } from './components/DocumentBrowser/FormEditor'
import type { Note } from './api/notes'

// ── Test data ─────────────────────────────────────────────────────

const PERSON_TEMPLATE: TemplateSchema = {
  template: 'person',
  note_type: 'person_note',
  description: 'Notes about a person',
  fields: [
    { name: 'name', type: 'string', required: true, description: "Person's full name" },
    { name: 'org', type: 'string', required: false, description: 'Organization' },
    { name: 'tags', type: 'list', required: false, description: 'Tags' },
    { name: 'active', type: 'boolean', required: false, description: 'Is active' },
  ],
}

const BASE_NOTE: Note = {
  file_path: 'people/alice.md',
  title: 'Alice Smith',
  body: 'Notes about Alice.',
  metadata: {
    type: 'person_note',
    template: 'person',
    domain: 'work',
    source: 'web',
    confidence: 0.85,
    review_status: 'pending',
    approved_by: null,
    approval_mode: null,
    people: [],
    tags: [],
    action_items: [],
    links: [],
    context: null,
    created: null,
    updated: null,
    org: null,
  } as Note['metadata'],
  mtime: 1711843200,
}

// FormEditor takes `templates` (plural array), not a single template
function renderForm(overrides?: {
  note?: Note
  templates?: TemplateSchema[]
  onChange?: (n: Note) => void
  onSave?: () => void
}) {
  const onChange = overrides?.onChange ?? vi.fn()
  const onSave = overrides?.onSave ?? vi.fn()
  return {
    onChange,
    onSave,
    ...render(
      <FormEditor
        note={overrides?.note ?? BASE_NOTE}
        templates={overrides?.templates ?? [PERSON_TEMPLATE]}
        onChange={onChange}
        onSave={onSave}
      />,
    ),
  }
}

// ── Tests ─────────────────────────────────────────────────────────

describe('FormEditor — rendering', () => {
  it('renders the form editor container', () => {
    renderForm()
    expect(screen.getByTestId('form-editor')).toBeInTheDocument()
  })

  it('renders all template fields', () => {
    renderForm()
    expect(screen.getByTestId('field-name')).toBeInTheDocument()
    expect(screen.getByTestId('field-org')).toBeInTheDocument()
    expect(screen.getByTestId('field-tags')).toBeInTheDocument()
    expect(screen.getByTestId('field-active')).toBeInTheDocument()
  })

  it('marks required fields with asterisk element', () => {
    renderForm()
    // The required span uses CSS class form-editor__required
    expect(document.querySelector('.form-editor__required')).not.toBeNull()
  })

  it('has exactly one required asterisk for one required field', () => {
    renderForm()
    const requiredSpans = document.querySelectorAll('.form-editor__required')
    // Only 'name' is required (1 of 4 fields)
    expect(requiredSpans.length).toBe(1)
  })

  it('renders string field as a text input', () => {
    renderForm()
    // data-testid is on the <input> itself for string fields
    const nameInput = screen.getByTestId('field-name') as HTMLInputElement
    expect(nameInput.tagName.toLowerCase()).toBe('input')
    expect(nameInput.type).toBe('text')
  })

  it('renders list field as a text input (comma-separated)', () => {
    renderForm()
    const tagsInput = screen.getByTestId('field-tags') as HTMLInputElement
    expect(tagsInput.tagName.toLowerCase()).toBe('input')
  })

  it('renders boolean field as a checkbox', () => {
    renderForm()
    // data-testid is on the <input type="checkbox"> inside BoolField
    const activeCheckbox = screen.getByTestId('field-active') as HTMLInputElement
    expect(activeCheckbox.tagName.toLowerCase()).toBe('input')
    expect(activeCheckbox.type).toBe('checkbox')
  })
})

describe('FormEditor — validation', () => {
  it('prevents save when required string field is empty', async () => {
    const onSave = vi.fn()
    // BASE_NOTE.metadata has no 'name' field → required validation fails
    renderForm({ onSave })

    fireEvent.click(screen.getByTestId('form-save-btn'))

    await waitFor(() => expect(screen.getByTestId('form-toast')).toBeInTheDocument())
    expect(onSave).not.toHaveBeenCalled()
  })

  it('shows error toast with validation message on invalid submit', async () => {
    renderForm()
    fireEvent.click(screen.getByTestId('form-save-btn'))
    await waitFor(() => {
      const toast = screen.getByTestId('form-toast')
      expect(toast.textContent).toMatch(/name/)
    })
  })

  it('calls onSave when all required fields are satisfied', async () => {
    const onSave = vi.fn()
    // A note that already has the required 'name' field populated in metadata
    const noteWithName: Note = {
      ...BASE_NOTE,
      metadata: { ...BASE_NOTE.metadata, name: 'Alice S.' } as Note['metadata'],
    }
    renderForm({ note: noteWithName, onSave })
    fireEvent.click(screen.getByTestId('form-save-btn'))
    await waitFor(() => expect(onSave).toHaveBeenCalled())
  })

  it('does not show error toast before first save attempt', () => {
    renderForm()
    expect(screen.queryByTestId('form-toast')).toBeNull()
  })
})

describe('FormEditor — field interaction', () => {
  it('calls onChange when a string field value changes', () => {
    const onChange = vi.fn()
    renderForm({ onChange })
    const orgInput = screen.getByTestId('field-org') as HTMLInputElement
    fireEvent.change(orgInput, { target: { value: 'Acme Corp' } })
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        metadata: expect.objectContaining({ org: 'Acme Corp' }),
      }),
    )
  })

  it('calls onChange when a boolean field is toggled', () => {
    const onChange = vi.fn()
    renderForm({ onChange })
    const activeCheckbox = screen.getByTestId('field-active') as HTMLInputElement
    fireEvent.click(activeCheckbox)
    expect(onChange).toHaveBeenCalled()
  })

  it('renders save button', () => {
    renderForm()
    expect(screen.getByTestId('form-save-btn')).toBeInTheDocument()
  })

  it('renders fallback form when no matching template found', () => {
    const noteWithOtherType: Note = {
      ...BASE_NOTE,
      metadata: { ...BASE_NOTE.metadata, type: 'unknown_type' } as unknown as Note['metadata'],
    }
    renderForm({ note: noteWithOtherType })
    // Falls back to minimal title-only form
    expect(screen.getByTestId('form-editor')).toBeInTheDocument()
    expect(screen.getByTestId('form-save-btn')).toBeInTheDocument()
  })
})
