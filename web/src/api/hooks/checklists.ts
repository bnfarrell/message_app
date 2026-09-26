import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type {
  AnswerPatch,
  ChecklistInstanceOut,
  ChecklistInstanceRowOut,
  ChecklistTemplateIn,
  ChecklistTemplateOut,
  ChecklistTemplatePatch,
} from '../types'

function ckPath(propertyId: string, rest: string): string {
  return propertyPath(propertyId, `checklists/${rest}`)
}

function qs(params: Record<string, string | boolean | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

/** Every checklist mutation refreshes every checklist query: the realtime event will do
 *  the same a moment later, but the actor should not wait for the round trip. */
function useCkMutation<TVars, TOut>(fn: (propertyId: string, vars: TVars) => Promise<TOut>) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<TOut, ApiError, TVars>({
    mutationFn: (vars) => fn(propertyId, vars),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.ckAll(propertyId) })
    },
  })
}

// ---- templates -----------------------------------------------------------------------------

export function useChecklistTemplates() {
  const { propertyId } = useSession()
  return useQuery<ChecklistTemplateOut[], ApiError>({
    queryKey: qk.ckTemplates(propertyId),
    queryFn: () => api<ChecklistTemplateOut[]>(ckPath(propertyId, 'templates')),
  })
}

export const useCreateChecklistTemplate = () =>
  useCkMutation<ChecklistTemplateIn, ChecklistTemplateOut>((p, body) =>
    api(ckPath(p, 'templates'), { method: 'POST', json: body }),
  )

export const usePatchChecklistTemplate = () =>
  useCkMutation<ChecklistTemplatePatch & { id: string }, ChecklistTemplateOut>(
    (p, { id, ...patch }) => api(ckPath(p, `templates/${id}`), { method: 'PATCH', json: patch }),
  )

// ---- instances -------------------------------------------------------------------------------

export type InstanceParams = { day?: string | null; departmentId?: string | null }

export function useChecklistInstances(params: InstanceParams = {}) {
  const { propertyId } = useSession()
  const normalised = { day: params.day ?? null, departmentId: params.departmentId ?? null }
  return useQuery<ChecklistInstanceRowOut[], ApiError>({
    queryKey: qk.ckInstances(propertyId, normalised),
    queryFn: () => api<ChecklistInstanceRowOut[]>(ckPath(propertyId, `instances${qs(normalised)}`)),
  })
}

export function useChecklistInstance(id: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<ChecklistInstanceOut, ApiError>({
    queryKey: qk.ckInstance(propertyId, id ?? ''),
    queryFn: () => api<ChecklistInstanceOut>(ckPath(propertyId, `instances/${id}`)),
    enabled: Boolean(id),
  })
}

export function useMissedChecklists(enabled: boolean) {
  const { propertyId } = useSession()
  return useQuery<ChecklistInstanceRowOut[], ApiError>({
    queryKey: qk.ckMissedAll(propertyId),
    queryFn: () => api<ChecklistInstanceRowOut[]>(ckPath(propertyId, 'missed?days=7')),
    enabled,
  })
}

export const useAssignChecklist = () =>
  useCkMutation<{ instanceId: string; userId: string | null }, ChecklistInstanceOut>(
    (p, { instanceId, userId }) =>
      api(ckPath(p, `instances/${instanceId}/assign`), { method: 'POST', json: { userId } }),
  )

export const useStartChecklist = () =>
  useCkMutation<string, ChecklistInstanceOut>((p, id) =>
    api(ckPath(p, `instances/${id}/start`), { method: 'POST' }),
  )

export const useStartOnDemand = () =>
  useCkMutation<string, ChecklistInstanceOut>((p, templateId) =>
    api(ckPath(p, `templates/${templateId}/start`), { method: 'POST' }),
  )

export const useSaveChecklistAnswer = () =>
  useCkMutation<{ instanceId: string; answerId: string; patch: AnswerPatch }, ChecklistInstanceOut>(
    (p, { instanceId, answerId, patch }) =>
      api(ckPath(p, `instances/${instanceId}/answers/${answerId}`), { method: 'PATCH', json: patch }),
  )

export const useSetChecklistComment = () =>
  useCkMutation<{ instanceId: string; comment: string }, ChecklistInstanceOut>(
    (p, { instanceId, comment }) =>
      api(ckPath(p, `instances/${instanceId}`), { method: 'PATCH', json: { comment } }),
  )

export const useCompleteChecklist = () =>
  useCkMutation<string, ChecklistInstanceOut>((p, id) =>
    api(ckPath(p, `instances/${id}/complete`), { method: 'POST' }),
  )

export const useUploadChecklistPhoto = () =>
  useCkMutation<{ instanceId: string; file: File; itemId?: string | null }, ChecklistInstanceOut>(
    (p, { instanceId, file, itemId }) => {
      const form = new FormData()
      form.set('photo', file)
      if (itemId) form.set('itemId', itemId)
      return api(ckPath(p, `instances/${instanceId}/photos`), { method: 'POST', body: form })
    },
  )
