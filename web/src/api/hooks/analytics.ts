import { useQuery } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type { AgentStats, Overview } from '../types'

export function useOverview(from: string, to: string) {
  const { propertyId } = useSession()
  return useQuery<Overview, ApiError>({
    queryKey: qk.analyticsOverview(propertyId, from, to),
    queryFn: () => api<Overview>(propertyPath(propertyId, `analytics/overview?from=${from}&to=${to}`)),
    staleTime: 60_000,
  })
}

export function useAgentStats(from: string, to: string) {
  const { propertyId } = useSession()
  return useQuery<AgentStats[], ApiError>({
    queryKey: qk.analyticsAgents(propertyId, from, to),
    queryFn: () => api<AgentStats[]>(propertyPath(propertyId, `analytics/agents?from=${from}&to=${to}`)),
    staleTime: 60_000,
  })
}
