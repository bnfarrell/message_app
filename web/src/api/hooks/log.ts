import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type {
  CreateLogEntryRequest,
  LogEntryOut,
  LogFeedOut,
  LogMentionableOut,
} from '../types'

export type LogFeedParams = {
  shift?: string | null
  departmentId?: string | null
  mentioningMe?: boolean
}

function toQuery(params: LogFeedParams): string {
  const search = new URLSearchParams()
  if (params.shift) search.set('shift', params.shift)
  if (params.departmentId) search.set('departmentId', params.departmentId)
  if (params.mentioningMe) search.set('mentioningMe', 'true')
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

export function useLogFeed(params: LogFeedParams = {}) {
  const { propertyId } = useSession()
  return useQuery<LogFeedOut, ApiError>({
    queryKey: qk.logFeed(propertyId, {
      shift: params.shift ?? null,
      departmentId: params.departmentId ?? null,
      mentioningMe: params.mentioningMe ?? false,
    }),
    queryFn: () => api<LogFeedOut>(propertyPath(propertyId, `log-entries${toQuery(params)}`)),
  })
}

export function useLogEntry(id: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<LogEntryOut, ApiError>({
    queryKey: qk.logEntry(propertyId, id ?? ''),
    queryFn: () => api<LogEntryOut>(propertyPath(propertyId, `log-entries/${id}`)),
    enabled: Boolean(id),
  })
}

export function useLogMentionables() {
  const { propertyId } = useSession()
  return useQuery<LogMentionableOut[], ApiError>({
    queryKey: qk.logMentionables(propertyId),
    queryFn: () => api<LogMentionableOut[]>(propertyPath(propertyId, 'log-entries/mentionables')),
  })
}

export function useCreateLogEntry() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<LogEntryOut, ApiError, CreateLogEntryRequest & { photo?: File }>({
    mutationFn: ({ photo, ...rest }) => {
      if (!photo) {
        return api<LogEntryOut>(propertyPath(propertyId, 'log-entries'), {
          method: 'POST',
          json: rest,
        })
      }
      // Multipart: the server reads scalars from request.form and the file from request.files,
      // so arrays go over as JSON strings. Matches SendStaffMessageRequest's handling.
      const form = new FormData()
      form.set('body', rest.body)
      if (rest.departmentId) form.set('departmentId', rest.departmentId)
      if (rest.mentions?.length) form.set('mentions', JSON.stringify(rest.mentions))
      if (rest.requiresAck) form.set('requiresAck', 'true')
      if (rest.ackAudience?.length) form.set('ackAudience', JSON.stringify(rest.ackAudience))
      form.set('photo', photo)
      return api<LogEntryOut>(propertyPath(propertyId, 'log-entries'), {
        method: 'POST',
        body: form,
      })
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.logFeedAll(propertyId) })
    },
  })
}

export function useAckLogEntry() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<LogEntryOut, ApiError, string>({
    mutationFn: (id) =>
      api<LogEntryOut>(propertyPath(propertyId, `log-entries/${id}/ack`), { method: 'POST' }),
    onSuccess: (entry) => {
      client.setQueryData(qk.logEntry(propertyId, entry.id), entry)
      void client.invalidateQueries({ queryKey: qk.logFeedAll(propertyId) })
    },
  })
}

export function useSetLogPinned() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<LogEntryOut, ApiError, { id: string; pinned: boolean }>({
    mutationFn: ({ id, pinned }) =>
      api<LogEntryOut>(propertyPath(propertyId, `log-entries/${id}/pin`), {
        method: pinned ? 'POST' : 'DELETE',
      }),
    onSuccess: (entry) => {
      client.setQueryData(qk.logEntry(propertyId, entry.id), entry)
      void client.invalidateQueries({ queryKey: qk.logFeedAll(propertyId) })
    },
  })
}
