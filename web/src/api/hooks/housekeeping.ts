import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type {
  HkAssignRequest,
  HkAssignmentOut,
  HkBoardOut,
  HkInspectionRowOut,
  HkReorderRequest,
  HkRoomDetailOut,
  HkRoomOut,
} from '../types'

function hkPath(propertyId: string, rest: string): string {
  return propertyPath(propertyId, `housekeeping/${rest}`)
}

export function useHkBoard() {
  const { propertyId } = useSession()
  return useQuery<HkBoardOut, ApiError>({
    queryKey: qk.hkBoardAll(propertyId),
    queryFn: () => api<HkBoardOut>(hkPath(propertyId, 'board')),
  })
}

export function useMyRooms() {
  const { propertyId } = useSession()
  return useQuery<HkRoomOut[], ApiError>({
    queryKey: qk.hkMyRoomsAll(propertyId),
    queryFn: () => api<HkRoomOut[]>(hkPath(propertyId, 'my-rooms')),
  })
}

export function useHkRoom(roomId: string | null) {
  const { propertyId } = useSession()
  return useQuery<HkRoomDetailOut, ApiError>({
    queryKey: qk.hkRoom(propertyId, roomId ?? ''),
    queryFn: () => api<HkRoomDetailOut>(hkPath(propertyId, `rooms/${roomId}`)),
    enabled: roomId !== null,
  })
}

export function useHkInspections() {
  const { propertyId } = useSession()
  return useQuery<HkInspectionRowOut[], ApiError>({
    queryKey: qk.hkInspectionsAll(propertyId),
    queryFn: () => api<HkInspectionRowOut[]>(hkPath(propertyId, 'inspections')),
  })
}

/** Every housekeeping mutation refreshes every housekeeping query: the realtime event will do
 *  the same a moment later, but the actor should not wait for the round trip. */
function useHkMutation<TVars, TOut>(fn: (propertyId: string, vars: TVars) => Promise<TOut>) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<TOut, ApiError, TVars>({
    mutationFn: (vars) => fn(propertyId, vars),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.hkAll(propertyId) })
    },
  })
}

export const useMarkDirty = () =>
  useHkMutation<{ roomId: string; note?: string | null }, HkRoomOut>((p, { roomId, note }) =>
    api(hkPath(p, `rooms/${roomId}/mark-dirty`), { method: 'POST', json: { note: note ?? null } }),
  )

export const useSetRush = () =>
  useHkMutation<{ roomId: string; on: boolean }, HkRoomOut>((p, { roomId, on }) =>
    api(hkPath(p, `rooms/${roomId}/rush`), { method: on ? 'POST' : 'DELETE' }),
  )

export const useSetRoomStatus = () =>
  useHkMutation<
    { roomId: string; status: 'out_of_order' | 'out_of_service' | 'dirty'; note?: string | null },
    HkRoomOut
  >((p, { roomId, status, note }) =>
    api(hkPath(p, `rooms/${roomId}/status`), { method: 'POST', json: { status, note: note ?? null } }),
  )

export const useAssignRooms = () =>
  useHkMutation<HkAssignRequest, HkAssignmentOut[]>((p, body) =>
    api(hkPath(p, 'assignments'), { method: 'POST', json: body }),
  )

export const useUnassign = () =>
  useHkMutation<string, HkRoomOut>((p, assignmentId) =>
    api(hkPath(p, `assignments/${assignmentId}`), { method: 'DELETE' }),
  )

export const useReorder = () =>
  useHkMutation<HkReorderRequest, HkAssignmentOut[]>((p, body) =>
    api(hkPath(p, 'assignments/reorder'), { method: 'POST', json: body }),
  )

export const useStartAssignment = () =>
  useHkMutation<string, HkRoomOut>((p, assignmentId) =>
    api(hkPath(p, `assignments/${assignmentId}/start`), { method: 'POST' }),
  )

export const useCompleteAssignment = () =>
  useHkMutation<string, HkRoomOut>((p, assignmentId) =>
    api(hkPath(p, `assignments/${assignmentId}/complete`), { method: 'POST' }),
  )

export const useInspectRoom = () =>
  useHkMutation<{ assignmentId: string; result: 'pass' | 'fail'; note?: string | null }, HkRoomOut>(
    (p, { assignmentId, result, note }) =>
      api(hkPath(p, `assignments/${assignmentId}/inspect`), {
        method: 'POST',
        json: { result, note: note ?? null },
      }),
  )

export const useSelfAssignStart = () =>
  useHkMutation<string, HkRoomOut>((p, roomId) =>
    api(hkPath(p, `rooms/${roomId}/self-assign-start`), { method: 'POST' }),
  )

export const useUploadHkPhoto = () =>
  useHkMutation<{ assignmentId: string; file: File }, HkRoomDetailOut>((p, { assignmentId, file }) => {
    const form = new FormData()
    form.set('photo', file)
    return api(hkPath(p, `assignments/${assignmentId}/photos`), { method: 'POST', body: form })
  })
