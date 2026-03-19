import type { components } from './schema.d.ts'
import { apiGet } from './client'

export type SearchResult = components['schemas']['SearchResult']
export type KeywordResult = components['schemas']['KeywordResult']

export interface SemanticSearchParams {
  q: string
  limit?: number
  threshold?: number
  type?: string
  domain?: string
  source?: string
}

export interface KeywordSearchParams {
  q: string
  limit?: number
  domain?: string
}

export function semanticSearch(params: SemanticSearchParams): Promise<SearchResult[]> {
  return apiGet<SearchResult[]>('/api/search', params as unknown as Record<string, string | number | boolean | null | undefined>)
}

export function keywordSearch(params: KeywordSearchParams): Promise<KeywordResult[]> {
  return apiGet<KeywordResult[]>('/api/search/keyword', params as unknown as Record<string, string | number | boolean | null | undefined>)
}
