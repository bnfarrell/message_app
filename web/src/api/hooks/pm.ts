import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type {
  AnswerPatch,
  ComplianceOut,
  CycleOut,
  InspectRequest,
  InspectionRowOut,
  PmUnitKind,
  RunOut,
  StartRunRequest,
  SweepOut,
  TemplateIn,
  TemplateOut,
  TemplatePatch,
  UnitImportOut,
  UnitIn,
  UnitOut,
  UnitPatch,
} from '../types'

function qs(params: Record<string, string | boolean | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

// ---- inventory --------------------------------------------------------------------------

export type UnitParams = { kind?: PmUnitKind | null; active?: boolean | null; q?: string | null }

export function useUnits(params: UnitParams = {}) {
  const { propertyId } = useSession()
  const normalised = {
    kind: params.kind ?? null,
    active: params.active ?? null,
    q: params.q ?? null,
  }
  return useQuery<UnitOut[], ApiError>({
    queryKey: qk.pmUnits(propertyId, normalised),
    queryFn: () => api<UnitOut[]>(propertyPath(propertyId, `maintainable-units${qs(normalised)}`)),
  })
}

export function useCreateUnit() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<UnitOut, ApiError, UnitIn>({
    mutationFn: (body) =>
      api<UnitOut>(propertyPath(propertyId, 'maintainable-units'), { method: 'POST', json: body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.pmUnitsAll(propertyId) })
      void client.invalidateQueries({ queryKey: qk.pmSweepAll(propertyId) })
    },
  })
}

export function usePatchUnit() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<UnitOut, ApiError, UnitPatch & { id: string }>({
    mutationFn: ({ id, ...patch }) =>
      api<UnitOut>(propertyPath(propertyId, `maintainable-units/${id}`), {
        method: 'PATCH',
        json: patch,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.pmUnitsAll(propertyId) })
      void client.invalidateQueries({ queryKey: qk.pmSweepAll(propertyId) })
    },
  })
}

export function useImportUnits() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<UnitImportOut, ApiError, File>({
    mutationFn: (file) => {
      const form = new FormData()
      form.set('file', file)
      return api<UnitImportOut>(propertyPath(propertyId, 'maintainable-units/import'), {
        method: 'POST',
        body: form,
      })
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.pmUnitsAll(propertyId) })
      void client.invalidateQueries({ queryKey: qk.pmSweepAll(propertyId) })
    },
  })
}

/** A rejected import is a 422 IMPORT_REJECTED whose `details` is the whole report. */
export function importReport(error: ApiError | null | undefined): UnitImportOut | null {
  if (!error || error.code !== 'IMPORT_REJECTED') return null
  return error.details as UnitImportOut
}

// ---- templates ---------------------------------------------------------------------------

export function usePmTemplates() {
  const { propertyId } = useSession()
  return useQuery<TemplateOut[], ApiError>({
    queryKey: qk.pmTemplates(propertyId),
    queryFn: () => api<TemplateOut[]>(propertyPath(propertyId, 'pm/templates')),
  })
}

export function useCreatePmTemplate() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<TemplateOut, ApiError, TemplateIn>({
    mutationFn: (body) =>
      api<TemplateOut>(propertyPath(propertyId, 'pm/templates'), { method: 'POST', json: body }),
    // Creating a sweep template opens its cycle, so the sweep page is stale too.
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.pmAll(propertyId) }),
  })
}

export function usePatchPmTemplate() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<TemplateOut, ApiError, TemplatePatch & { id: string }>({
    mutationFn: ({ id, ...patch }) =>
      api<TemplateOut>(propertyPath(propertyId, `pm/templates/${id}`), {
        method: 'PATCH',
        json: patch,
      }),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.pmAll(propertyId) }),
  })
}

// ---- sweep, cycles ----------------------------------------------------------------------

export type SweepParams = {
  kind: PmUnitKind
  status?: 'remaining' | 'completed' | null
  q?: string | null
  sort?: string | null
}

export function useSweep(params: SweepParams) {
  const { propertyId } = useSession()
  const normalised = {
    kind: params.kind,
    status: params.status ?? null,
    q: params.q ?? null,
    sort: params.sort ?? null,
  }
  return useQuery<SweepOut, ApiError>({
    queryKey: qk.pmSweep(propertyId, normalised),
    queryFn: () => api<SweepOut>(propertyPath(propertyId, `pm/sweep${qs(normalised)}`)),
  })
}

export function usePmCycles(templateId: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<CycleOut[], ApiError>({
    queryKey: qk.pmCycles(propertyId, templateId ?? ''),
    queryFn: () => api<CycleOut[]>(propertyPath(propertyId, `pm/cycles?templateId=${templateId}`)),
    enabled: Boolean(templateId),
  })
}

// ---- runs --------------------------------------------------------------------------------

export function usePmRun(id: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<RunOut, ApiError>({
    queryKey: qk.pmRun(propertyId, id ?? ''),
    queryFn: () => api<RunOut>(propertyPath(propertyId, `pm/runs/${id}`)),
    enabled: Boolean(id),
  })
}

/** Every run mutation answers with the whole RunOut; caching it here means the checklist
 *  never renders a stale `missingRequired` between the save and a refetch. */
function useRunMutation<TVars>(
  request: (propertyId: string, vars: TVars) => Promise<RunOut>,
  // `qk.*` return readonly tuples, so the element type must be readonly too.
  alsoInvalidate: (propertyId: string) => readonly (readonly unknown[])[] = () => [],
) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<RunOut, ApiError, TVars>({
    mutationFn: (vars) => request(propertyId, vars),
    onSuccess: (run) => {
      client.setQueryData(qk.pmRun(propertyId, run.id), run)
      for (const key of alsoInvalidate(propertyId)) void client.invalidateQueries({ queryKey: key })
    },
  })
}

export const useStartRun = () =>
  useRunMutation<StartRunRequest>(
    (propertyId, body) =>
      api<RunOut>(propertyPath(propertyId, 'pm/runs'), { method: 'POST', json: body }),
    (propertyId) => [qk.pmSweepAll(propertyId)],
  )

export const useBeginRun = () =>
  useRunMutation<string>(
    (propertyId, runId) =>
      api<RunOut>(propertyPath(propertyId, `pm/runs/${runId}/start`), { method: 'POST' }),
    (propertyId) => [qk.workOrdersAll(propertyId)],
  )

export const useSaveAnswer = () =>
  useRunMutation<{ runId: string; answerId: string; patch: AnswerPatch }>(
    (propertyId, { runId, answerId, patch }) =>
      api<RunOut>(propertyPath(propertyId, `pm/runs/${runId}/answers/${answerId}`), {
        method: 'PATCH',
        json: patch,
      }),
  )

export const useUploadRunPhoto = () =>
  useRunMutation<{ runId: string; file: File; itemId?: string | null }>(
    (propertyId, { runId, file, itemId }) => {
      const form = new FormData()
      form.set('photo', file)
      if (itemId) form.set('itemId', itemId)
      return api<RunOut>(propertyPath(propertyId, `pm/runs/${runId}/photos`), {
        method: 'POST',
        body: form,
      })
    },
  )

export const useCompleteRun = () =>
  useRunMutation<string>(
    (propertyId, runId) =>
      api<RunOut>(propertyPath(propertyId, `pm/runs/${runId}/complete`), { method: 'POST' }),
    (propertyId) => [
      qk.pmSweepAll(propertyId),
      qk.pmInspectionsAll(propertyId),
      qk.workOrdersAll(propertyId),
    ],
  )

export const useInspectRun = () =>
  useRunMutation<{ runId: string; body: InspectRequest }>(
    (propertyId, { runId, body }) =>
      api<RunOut>(propertyPath(propertyId, `pm/runs/${runId}/inspect`), {
        method: 'POST',
        json: body,
      }),
    (propertyId) => [
      qk.pmSweepAll(propertyId),
      qk.pmInspectionsAll(propertyId),
      qk.pmCyclesAll(propertyId),
      qk.workOrdersAll(propertyId),
    ],
  )

// ---- inspection queue, compliance --------------------------------------------------------

export type InspectionParams = {
  kind?: PmUnitKind | null
  status: 'available' | 'inspected'
  sort?: 'days_since_last_pm' | 'completed_at' | null
}

export function useInspections(params: InspectionParams) {
  const { propertyId } = useSession()
  const normalised = { kind: params.kind ?? null, status: params.status, sort: params.sort ?? null }
  return useQuery<InspectionRowOut[], ApiError>({
    queryKey: qk.pmInspections(propertyId, normalised),
    queryFn: () =>
      api<InspectionRowOut[]>(propertyPath(propertyId, `pm/inspections${qs(normalised)}`)),
  })
}

export function useCompliance(from: string, to: string) {
  const { propertyId } = useSession()
  return useQuery<ComplianceOut, ApiError>({
    queryKey: qk.pmCompliance(propertyId, from, to),
    queryFn: () =>
      api<ComplianceOut>(propertyPath(propertyId, `pm/compliance?from=${from}&to=${to}`)),
    enabled: Boolean(from && to),
  })
}
