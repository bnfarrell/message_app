import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type {
  AddParticipantsRequest,
  CreateStaffConversationRequest,
  GroupPatch,
  StaffConversationDetail,
  StaffConversationOut,
  StaffDirectoryEntryOut,
  StaffMessageOut,
} from '../types'

export function useStaffConversations() {
  const { propertyId } = useSession()
  return useQuery<StaffConversationOut[], ApiError>({
    queryKey: qk.staffConversationsAll(propertyId),
    queryFn: () => api<StaffConversationOut[]>(propertyPath(propertyId, 'staff-conversations')),
  })
}

export function useStaffConversation(id: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<StaffConversationDetail, ApiError>({
    queryKey: qk.staffConversation(propertyId, id ?? ''),
    queryFn: () =>
      api<StaffConversationDetail>(propertyPath(propertyId, `staff-conversations/${id}`)),
    enabled: Boolean(id),
  })
}

export function useStaffDirectory() {
  const { propertyId } = useSession()
  return useQuery<StaffDirectoryEntryOut[], ApiError>({
    queryKey: qk.staffDirectory(propertyId),
    queryFn: () => api<StaffDirectoryEntryOut[]>(propertyPath(propertyId, 'staff-directory')),
  })
}

export function useCreateStaffConversation() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<StaffConversationDetail, ApiError, CreateStaffConversationRequest>({
    mutationFn: (body) =>
      api<StaffConversationDetail>(propertyPath(propertyId, 'staff-conversations'), {
        method: 'POST',
        json: body,
      }),
    onSuccess: (conv) => {
      void client.invalidateQueries({ queryKey: qk.staffConversationsAll(propertyId) })
      client.setQueryData(qk.staffConversation(propertyId, conv.id), conv)
    },
  })
}

export function useSendStaffMessage(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<StaffMessageOut, ApiError, { body?: string; photo?: File }>({
    mutationFn: ({ body, photo }) => {
      const form = new FormData()
      if (body) form.set('body', body)
      if (photo) form.set('photo', photo)
      return api<StaffMessageOut>(
        propertyPath(propertyId, `staff-conversations/${conversationId}/messages`),
        { method: 'POST', body: form },
      )
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.staffConversation(propertyId, conversationId) })
      void client.invalidateQueries({ queryKey: qk.staffConversationsAll(propertyId) })
    },
  })
}

export function useMarkStaffConversationRead(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<void, ApiError, void>({
    mutationFn: () =>
      api<void>(propertyPath(propertyId, `staff-conversations/${conversationId}/read`), {
        method: 'POST',
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.staffConversationsAll(propertyId) })
    },
  })
}

export function useUpdateStaffGroup(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<StaffConversationDetail, ApiError, GroupPatch>({
    mutationFn: (body) =>
      api<StaffConversationDetail>(
        propertyPath(propertyId, `staff-conversations/${conversationId}`),
        { method: 'PATCH', json: body },
      ),
    onSuccess: (conv) => {
      client.setQueryData(qk.staffConversation(propertyId, conversationId), conv)
      void client.invalidateQueries({ queryKey: qk.staffConversationsAll(propertyId) })
    },
  })
}

export function useAddStaffParticipants(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<StaffConversationDetail, ApiError, AddParticipantsRequest>({
    mutationFn: (body) =>
      api<StaffConversationDetail>(
        propertyPath(propertyId, `staff-conversations/${conversationId}/participants`),
        { method: 'POST', json: body },
      ),
    onSuccess: (conv) => {
      client.setQueryData(qk.staffConversation(propertyId, conversationId), conv)
    },
  })
}

export function useRemoveStaffParticipant(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<StaffConversationDetail | void, ApiError, { userId: string }>({
    mutationFn: ({ userId }) =>
      api<StaffConversationDetail | void>(
        propertyPath(propertyId, `staff-conversations/${conversationId}/participants/${userId}`),
        { method: 'DELETE' },
      ),
    onSuccess: (conv) => {
      void client.invalidateQueries({ queryKey: qk.staffConversationsAll(propertyId) })
      if (conv) client.setQueryData(qk.staffConversation(propertyId, conversationId), conv)
    },
  })
}
