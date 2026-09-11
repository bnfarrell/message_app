import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type {
  CreateStaffRequest, DepartmentIn, DepartmentOut, DepartmentPatch, GuestDetail, StaffPatch,
  StaffUserOut,
} from '../types'

export function useDepartments() {
  const { propertyId } = useSession()
  return useQuery<DepartmentOut[], ApiError>({
    queryKey: qk.departments(propertyId),
    queryFn: () => api<DepartmentOut[]>(propertyPath(propertyId, 'departments')),
    staleTime: 5 * 60_000, // departments change about never
  })
}

/**
 * Department pickers on Users, Quick replies, Digital assets, the inbox filter and the work-order
 * form all read `useDepartments`, so a mutation that did not invalidate `qk.departments` would show
 * up as a wrong dropdown three screens away rather than as a broken Departments screen. That key is
 * the whole prefix — `['departments', propertyId]` — so invalidating it reaches every reader.
 */
function useDepartmentWrite<TBody, TResult>(method: 'POST' | 'PATCH' | 'DELETE') {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<TResult, ApiError, TBody & { id?: string }>({
    mutationFn: (body) => {
      const { id, ...rest } = body as { id?: string }
      const path = propertyPath(propertyId, id ? `departments/${id}` : 'departments')
      return api<TResult>(path, { method, json: method === 'DELETE' ? undefined : rest })
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.departments(propertyId) }),
  })
}

export const useCreateDepartment = () => useDepartmentWrite<DepartmentIn, DepartmentOut>('POST')
export const usePatchDepartment = () => useDepartmentWrite<DepartmentPatch, DepartmentOut>('PATCH')
/** 409 CONFLICT while the department is still referenced; its `message` names what to fix. */
export const useDeleteDepartment = () => useDepartmentWrite<{ id: string }, void>('DELETE')

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
