import { describe, it, expect } from 'vitest'
import { metaToYaml, buildRawDoc, splitFrontmatter, parseFrontmatter } from './yamlUtils'

// ── metaToYaml ────────────────────────────────────────────────────

describe('metaToYaml — scalar values', () => {
  it('serializes a plain string', () => {
    expect(metaToYaml({ key: 'hello' })).toBe('key: hello')
  })

  it('serializes a boolean true', () => {
    expect(metaToYaml({ active: true })).toBe('active: true')
  })

  it('serializes a boolean false', () => {
    expect(metaToYaml({ active: false })).toBe('active: false')
  })

  it('serializes a float number', () => {
    expect(metaToYaml({ confidence: 0.85 })).toBe('confidence: 0.85')
  })

  it('serializes null as bare key', () => {
    expect(metaToYaml({ org: null })).toBe('org:')
  })

  it('skips undefined values', () => {
    expect(metaToYaml({ a: 1, b: undefined })).toBe('a: 1')
  })
})

describe('metaToYaml — string quoting', () => {
  it('quotes strings containing a colon', () => {
    const result = metaToYaml({ key: 'value: with colon' })
    expect(result).toContain('"')
    expect(result).toContain('value: with colon')
  })

  it('quotes strings starting with !', () => {
    const result = metaToYaml({ key: '!important' })
    // Must be quoted — bare `!important` is a YAML tag
    expect(result).toContain('"')
    expect(result).not.toBe('key: !important')
  })

  it('quotes strings that look like numbers', () => {
    const result = metaToYaml({ val: '42' })
    expect(result).toContain('"42"')
  })

  it('quotes the literal string "null"', () => {
    const result = metaToYaml({ key: 'null' })
    expect(result).toContain('"null"')
  })

  it('quotes the literal string "true"', () => {
    const result = metaToYaml({ key: 'true' })
    expect(result).toContain('"true"')
  })

  it('quotes strings with leading/trailing whitespace', () => {
    const result = metaToYaml({ key: ' padded ' })
    expect(result).toContain('"')
  })

  it('quotes empty strings', () => {
    const result = metaToYaml({ key: '' })
    expect(result).toContain('""')
  })
})

describe('metaToYaml — arrays', () => {
  it('serializes empty arrays inline', () => {
    expect(metaToYaml({ tags: [] })).toBe('tags: []')
  })

  it('serializes a non-empty array as block sequence', () => {
    expect(metaToYaml({ tags: ['a', 'b'] })).toBe('tags:\n  - a\n  - b')
  })

  it('serializes array items that are objects via JSON', () => {
    const result = metaToYaml({ links: [{ href: 'https://example.com', title: 'Ex' }] })
    expect(result).toContain('- {')
    expect(result).toContain('href')
  })
})

// ── buildRawDoc / splitFrontmatter / parseFrontmatter round-trips ──

describe('round-trip: buildRawDoc → splitFrontmatter → parseFrontmatter', () => {
  it('round-trips a simple note', () => {
    const meta = { type: 'person_note', domain: 'work', confidence: 0.85, active: true }
    const raw = buildRawDoc('Alice', meta, 'Body text')
    const { frontmatter, body } = splitFrontmatter(raw)
    const parsed = parseFrontmatter(frontmatter)
    expect(parsed.title).toBe('Alice')
    expect(parsed.type).toBe('person_note')
    expect(parsed.domain).toBe('work')
    expect(parsed.confidence).toBe(0.85)
    expect(parsed.active).toBe(true)
    expect(body).toBe('Body text')
  })

  it('round-trips null values', () => {
    const raw = buildRawDoc('Note', { org: null }, '')
    const parsed = parseFrontmatter(splitFrontmatter(raw).frontmatter)
    expect(parsed.org).toBeNull()
  })

  it('round-trips a non-empty tags array', () => {
    const raw = buildRawDoc('Note', { tags: ['react', 'typescript'] }, '')
    const parsed = parseFrontmatter(splitFrontmatter(raw).frontmatter)
    expect(parsed.tags).toEqual(['react', 'typescript'])
  })

  it('round-trips an empty array', () => {
    const raw = buildRawDoc('Note', { tags: [] }, '')
    const parsed = parseFrontmatter(splitFrontmatter(raw).frontmatter)
    expect(parsed.tags).toEqual([])
  })

  it('round-trips a string containing YAML special chars', () => {
    const raw = buildRawDoc('Note', { info: 'key: value' }, '')
    const parsed = parseFrontmatter(splitFrontmatter(raw).frontmatter)
    expect(parsed.info).toBe('key: value')
  })

  it('round-trips a string starting with !', () => {
    const raw = buildRawDoc('Note', { priority: '!critical' }, '')
    const parsed = parseFrontmatter(splitFrontmatter(raw).frontmatter)
    expect(parsed.priority).toBe('!critical')
  })

  it('puts title first in the frontmatter', () => {
    const raw = buildRawDoc('My Title', { type: 'idea' }, '')
    expect(raw).toMatch(/^---\ntitle: My Title/)
  })
})

// ── splitFrontmatter edge cases ───────────────────────────────────

describe('splitFrontmatter', () => {
  it('returns the full string as body when there is no frontmatter', () => {
    const { frontmatter, body } = splitFrontmatter('Just plain text')
    expect(frontmatter).toBe('')
    expect(body).toBe('Just plain text')
  })

  it('handles CRLF line endings', () => {
    const { frontmatter, body } = splitFrontmatter('---\r\ntitle: T\r\n---\r\nBody')
    expect(frontmatter).toBe('title: T')
    expect(body).toBe('Body')
  })
})
