import { useMutation, useQuery } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type { AssetOut, CategoryOut, QuickReplyOut, RenderedQuickReply } from '../types'

export function useQuickReplies(q?: string) {
  const { propertyId } = useSession()
  return useQuery<QuickReplyOut[], ApiError>({
    queryKey: qk.quickReplies(propertyId, q),
    queryFn: () =>
      api<QuickReplyOut[]>(
        propertyPath(propertyId, `quick-replies${q ? `?q=${encodeURIComponent(q)}` : ''}`),
      ),
    staleTime: 60_000,
  })
}

export function useRenderQuickReply() {
  const { propertyId } = useSession()
  return useMutation<RenderedQuickReply, ApiError, { id: string; conversationId: string }>({
    mutationFn: ({ id, conversationId }) =>
      api<RenderedQuickReply>(propertyPath(propertyId, `quick-replies/${id}/render`), {
        method: 'POST',
        json: { conversationId },
      }),
  })
}

export function useAssets() {
  const { propertyId } = useSession()
  return useQuery<AssetOut[], ApiError>({
    queryKey: qk.assets(propertyId),
    queryFn: () => api<AssetOut[]>(propertyPath(propertyId, 'assets')),
    staleTime: 60_000,
  })
}

export function useCategories() {
  const { propertyId } = useSession()
  return useQuery<CategoryOut[], ApiError>({
    queryKey: qk.categories(propertyId),
    queryFn: () => api<CategoryOut[]>(propertyPath(propertyId, 'resolution-categories')),
    staleTime: 5 * 60_000,
  })
}
