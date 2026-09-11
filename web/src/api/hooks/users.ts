import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type { CreateStaffRequest, DepartmentOut, GuestDetail, StaffPatch, StaffUserOut } from '../types'

export function useDepartments() {
  const { propertyId } = useSession()
  return useQuery<DepartmentOut[], ApiError>({
    queryKey: qk.departments(propertyId),
    queryFn: () => api<DepartmentOut[]>(propertyPath(propertyId, 'departments')),
    staleTime: 5 * 60_000, // departments change about never
  })
}

export function useStaff() {
  const { propertyId } = useSession()
  return useQuery<StaffUserOut[], ApiError>({
    queryKey: qk.staff(propertyId),
    queryFn: () => api<StaffUserOut[]>(propertyPath(propertyId, 'users')),
    staleTime: 5 * 60_000,
  })
}

export function useGuest(id: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<GuestDetail, ApiError>({
    queryKey: qk.guest(propertyId, id ?? ''),
    queryFn: () => api<GuestDetail>(propertyPath(propertyId, `guests/${id}`)),
    enabled: Boolean(id),
  })
}

export function useCreateStaff() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<StaffUserOut, ApiError, CreateStaffRequest>({
    mutationFn: (body) => api<StaffUserOut>(propertyPath(propertyId, 'users'), { method: 'POST', json: body }),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.staffAll(propertyId) }),
  })
}

export function usePatchStaff() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<StaffUserOut, ApiError, StaffPatch & { id: string }>({
    mutationFn: ({ id, ...patch }) =>
      api<StaffUserOut>(propertyPath(propertyId, `users/${id}`), { method: 'PATCH', json: patch }),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.staffAll(propertyId) }),
  })
}

export function useDeleteStaff() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<void, ApiError, { id: string }>({
    mutationFn: ({ id }) => api<void>(propertyPath(propertyId, `users/${id}`), { method: 'DELETE' }),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.staffAll(propertyId) }),
  })
}
