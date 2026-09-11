import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type {
  AssetIn, AssetOut, AssetPatch, CategoryIn, CategoryOut, CategoryPatch,
  PreviewRequest, QuickReplyIn, QuickReplyOut, QuickReplyPatch, RenderedQuickReply,
} from '../types'

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

/** The names the server's interpolator actually supports; the mockup's list is stale. */
export function useQuickReplyVariables() {
  const { propertyId } = useSession()
  return useQuery<string[], ApiError>({
    queryKey: qk.quickReplyVariables(propertyId),
    queryFn: () => api<string[]>(propertyPath(propertyId, 'quick-replies/variables')),
    staleTime: Infinity, // a code-level constant on the server
  })
}

/**
 * Renders an unsaved body against the server's sample values, and returns the authoritative
 * `segments`/`characters`. Deliberately `/preview`, not `/render`: `/render` bumps `usageCount`,
 * needs a saved row plus a real conversation, and is gated on `reply`, which `corporate` — a role
 * that reaches this screen — does not hold. Pass an already-debounced body; the key is the body.
 */
export function useQuickReplyPreview(body: string) {
  const { propertyId } = useSession()
  return useQuery<RenderedQuickReply, ApiError>({
    queryKey: qk.quickReplyPreview(propertyId, body),
    queryFn: () =>
      api<RenderedQuickReply>(propertyPath(propertyId, 'quick-replies/preview'), {
        method: 'POST',
        json: { body } satisfies PreviewRequest,
      }),
    enabled: body.length > 0, // the server rejects an empty body with a 400
    staleTime: 5 * 60_000,
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

// Create/patch share a body shape per resource; delete only ever needs the id. Invalidating the
// `*All` prefix (not the exact list key, which for quick replies varies by search term) is what
// makes a write show up in every active view of that resource, filtered or not.
function useWrite<TBody, TResult>(
  path: string,
  method: 'POST' | 'PATCH' | 'DELETE',
  invalidate: (propertyId: string) => readonly unknown[],
) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<TResult, ApiError, TBody & { id?: string }>({
    mutationFn: (body) => {
      const { id, ...rest } = body as { id?: string }
      const url = propertyPath(propertyId, id ? `${path}/${id}` : path)
      return api<TResult>(url, { method, json: method === 'DELETE' ? undefined : rest })
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: invalidate(propertyId) })
    },
  })
}

export const useCreateQuickReply = () =>
  useWrite<QuickReplyIn, QuickReplyOut>('quick-replies', 'POST', (p) => qk.quickRepliesAll(p))
export const usePatchQuickReply = () =>
  useWrite<QuickReplyPatch, QuickReplyOut>('quick-replies', 'PATCH', (p) => qk.quickRepliesAll(p))
export const useDeleteQuickReply = () =>
  useWrite<{ id: string }, void>('quick-replies', 'DELETE', (p) => qk.quickRepliesAll(p))

export const useCreateAsset = () =>
  useWrite<AssetIn, AssetOut>('assets', 'POST', (p) => qk.assetsAll(p))
export const usePatchAsset = () =>
  useWrite<AssetPatch, AssetOut>('assets', 'PATCH', (p) => qk.assetsAll(p))
export const useDeleteAsset = () =>
  useWrite<{ id: string }, void>('assets', 'DELETE', (p) => qk.assetsAll(p))

export const useCreateCategory = () =>
  useWrite<CategoryIn, CategoryOut>('resolution-categories', 'POST', (p) => qk.categoriesAll(p))
export const usePatchCategory = () =>
  useWrite<CategoryPatch, CategoryOut>('resolution-categories', 'PATCH', (p) => qk.categoriesAll(p))
export const useDeleteCategory = () =>
  useWrite<{ id: string }, void>('resolution-categories', 'DELETE', (p) => qk.categoriesAll(p))
