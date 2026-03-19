import { apiGet } from './client'

export interface GraphNode {
  id: string
  label: string
  type: string
  degree: number | null
  weight: number
}

export interface GraphEdge {
  source: string
  target: string
  edge_type: string
  relation: string
  weight: number
  metadata: Record<string, unknown>
}

export interface GraphData {
  focus: string | null
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface GraphParams {
  focus?: string
  max_degree?: number
  types?: string
  n?: number
}

export function getGraph(params?: GraphParams): Promise<GraphData> {
  return apiGet<GraphData>('/api/graph', params as Record<string, string | number | boolean | null | undefined>)
}
