import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type { PropertySettingsOut, PropertySettingsPatch } from '../types'

/** Readable by any member; only `manage_admin` may PATCH. */
export function usePropertySettings() {
  const { propertyId } = useSession()
  return useQuery<PropertySettingsOut, ApiError>({
    queryKey: qk.propertySettings(propertyId),
    queryFn: () => api<PropertySettingsOut>(propertyPath(propertyId, 'settings')),
    // The settings screen seeds its form from this data, so a background refetch — on window
    // focus, say — would replace a half-typed draft with the stored record. The save below writes
    // the server's own response back into the cache, so nothing goes stale while the screen is up.
    staleTime: Infinity,
  })
}

/**
 * The response is the full settings object *after* normalisation — phone and smsNumber come back
 * E.164 and currency upper-cased, not as they were typed — so it is written straight into the
 * cache rather than merely invalidated. Re-reading it into the form is the point: an admin who
 * typed "(555) 012-3456" needs to see what was actually stored.
 */
export function usePatchPropertySettings() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<PropertySettingsOut, ApiError, PropertySettingsPatch>({
    mutationFn: (patch) =>
      api<PropertySettingsOut>(propertyPath(propertyId, 'settings'), {
        method: 'PATCH',
        json: patch,
      }),
    onSuccess: (settings) => client.setQueryData(qk.propertySettings(propertyId), settings),
  })
}
