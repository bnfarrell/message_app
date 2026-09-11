import { useQuery } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type { DepartmentOut, GuestDetail, StaffUserOut } from '../types'

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
