/**
 * Minimal YAML serializer/parser scoped to NoteMetadata frontmatter.
 *
 * Handles: strings, numbers, booleans, null, flat arrays of scalars or JSON objects.
 * Does NOT handle deeply-nested YAML — we only need the known field subset.
 */

/** Serialize a metadata object into YAML-style key:value lines. */
export function metaToYaml(meta: Record<string, unknown>): string {
  const lines: string[] = []
  for (const [key, value] of Object.entries(meta)) {
    if (value === undefined) continue
    if (value === null) {
      lines.push(`${key}:`)
    } else if (typeof value === 'boolean') {
      lines.push(`${key}: ${value}`)
    } else if (typeof value === 'number') {
      lines.push(`${key}: ${value}`)
    } else if (Array.isArray(value)) {
      if (value.length === 0) {
        lines.push(`${key}: []`)
      } else {
        lines.push(`${key}:`)
        for (const item of value) {
          const s = typeof item === 'object' && item !== null ? JSON.stringify(item) : String(item)
          lines.push(`  - ${s}`)
        }
      }
    } else {
      const s = String(value)
      // Quote strings that contain YAML-special chars or look like other types
      if (
        /[:#\[\]{},|>&*'"?!]/.test(s) ||
        s.trim() !== s ||
        s === '' ||
        s === 'null' ||
        s === 'true' ||
        s === 'false' ||
        /^-?\d/.test(s)
      ) {
        lines.push(`${key}: ${JSON.stringify(s)}`)
      } else {
        lines.push(`${key}: ${s}`)
      }
    }
  }
  return lines.join('\n')
}

/** Construct a raw document string: YAML frontmatter + blank line + markdown body. */
export function buildRawDoc(
  title: string,
  metadata: Record<string, unknown>,
  body: string,
): string {
  // Put title first, then remaining metadata fields
  const { title: _t, ...rest } = metadata as { title?: unknown } & Record<string, unknown>
  const frontmatter = metaToYaml({ title, ...rest })
  return `---\n${frontmatter}\n---\n\n${body}`
}

/** Split raw document text into frontmatter YAML string and markdown body. */
export function splitFrontmatter(raw: string): { frontmatter: string; body: string } {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)/.exec(raw)
  if (!match) return { frontmatter: '', body: raw }
  return { frontmatter: match[1], body: match[2].trimStart() }
}

/** Parse a flat YAML frontmatter string into a plain object. */
export function parseFrontmatter(yaml: string): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  const lines = yaml.split('\n')
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim() || line.trimStart().startsWith('#')) {
      i++
      continue
    }
    // Match "key: rest" or "key:"
    const kv = /^(\w[\w\s_-]*?):\s*(.*)$/.exec(line)
    if (!kv) {
      i++
      continue
    }
    const key = kv[1].trim()
    const rest = kv[2].trim()

    if (rest === '[]') {
      result[key] = []
      i++
    } else if (rest === '' || rest === 'null' || rest === '~') {
      // Could be null or a sequence on next lines
      const items: unknown[] = []
      i++
      while (i < lines.length && /^\s{2}-\s/.test(lines[i])) {
        const m = /^\s{2}-\s+(.*)/.exec(lines[i])
        if (m) items.push(parseScalar(m[1]))
        i++
      }
      result[key] = items.length > 0 ? items : null
    } else {
      result[key] = parseScalar(rest)
      i++
    }
  }
  return result
}

function parseScalar(s: string): unknown {
  if (s === 'null' || s === '~') return null
  if (s === 'true') return true
  if (s === 'false') return false
  if (/^-?\d+(\.\d+)?$/.test(s)) return Number(s)
  if (s.startsWith('"') && s.endsWith('"')) {
    try { return JSON.parse(s) } catch { return s }
  }
  if (s.startsWith('{') || s.startsWith('[')) {
    try { return JSON.parse(s) } catch { return s }
  }
  return s
}
