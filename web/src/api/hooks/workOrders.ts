import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type {
  CreateWorkOrder,
  WorkOrderDetail,
  WorkOrderOut,
  WorkOrderPatch,
  WorkOrderPhotoOut,
  WorkOrderPrefill,
} from '../types'

export type WorkOrderParams = {
  status?: string | null
  type?: string | null
  dept?: string | null
  assignee?: string | null
  mine?: boolean
  includeClosed?: boolean
}

export function useWorkOrders(params: WorkOrderParams = {}) {
  const { propertyId } = useSession()
  const search = new URLSearchParams()
  if (params.status) search.set('status', params.status)
  if (params.type) search.set('type', params.type)
  if (params.dept) search.set('dept', params.dept)
  if (params.assignee) search.set('assignee', params.assignee)
  if (params.mine) search.set('mine', 'true')
  if (params.includeClosed) search.set('includeClosed', 'true')

  return useQuery<WorkOrderOut[], ApiError>({
    queryKey: qk.workOrders(propertyId, { ...params } as Record<string, string | boolean | null>),
    queryFn: () =>
      api<WorkOrderOut[]>(propertyPath(propertyId, `work-orders${search.size ? `?${search}` : ''}`)),
  })
}

export function useWorkOrder(id: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<WorkOrderDetail, ApiError>({
    queryKey: qk.workOrder(propertyId, id ?? ''),
    queryFn: () => api<WorkOrderDetail>(propertyPath(propertyId, `work-orders/${id}`)),
    enabled: Boolean(id),
  })
}

export function useWorkOrderPrefill(conversationId: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<WorkOrderPrefill, ApiError>({
    queryKey: qk.workOrderPrefill(propertyId, conversationId ?? ''),
    queryFn: () =>
      api<WorkOrderPrefill>(
        propertyPath(propertyId, `work-orders/prefill?conversationId=${conversationId}`),
      ),
    enabled: Boolean(conversationId),
    staleTime: 0, // the suggestion depends on the last inbound message
  })
}

export function useCreateWorkOrder() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<WorkOrderOut, ApiError, CreateWorkOrder>({
    mutationFn: (body) =>
      api<WorkOrderOut>(propertyPath(propertyId, 'work-orders'), { method: 'POST', json: body }),
    onSuccess: (created) => {
      void client.invalidateQueries({ queryKey: qk.workOrdersAll(propertyId) })
      if (created.sourceConversationId) {
        void client.invalidateQueries({
          queryKey: qk.conversation(propertyId, created.sourceConversationId),
        })
      }
    },
  })
}

export function useUploadWorkOrderPhoto(id: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<WorkOrderPhotoOut, ApiError, { file: File; kind: 'before' | 'after' }>({
    mutationFn: ({ file, kind }) => {
      const form = new FormData()
      form.set('photo', file)
      form.set('kind', kind)
      // No Content-Type here — the browser sets the multipart boundary itself.
      return api<WorkOrderPhotoOut>(propertyPath(propertyId, `work-orders/${id}/photos`), {
        method: 'POST',
        body: form,
      })
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.workOrder(propertyId, id) })
    },
  })
}

export function usePatchWorkOrder(id: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<WorkOrderDetail, ApiError, WorkOrderPatch>({
    mutationFn: (patch) =>
      api<WorkOrderDetail>(propertyPath(propertyId, `work-orders/${id}`), {
        method: 'PATCH',
        json: patch,
      }),
    onSuccess: (updated) => {
      void client.invalidateQueries({ queryKey: qk.workOrder(propertyId, id) })
      void client.invalidateQueries({ queryKey: qk.workOrdersAll(propertyId) })
      // Completing a WO raised from a conversation creates a draft prompt there.
      if (updated.sourceConversationId) {
        void client.invalidateQueries({
          queryKey: qk.conversation(propertyId, updated.sourceConversationId),
        })
      }
    },
  })
}
