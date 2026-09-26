import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type RenderResult, render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { qk } from '../api/queryKeys'
import type { DepartmentType, MembershipOut, Role, SessionOut } from '../api/types'

export function sessionFixture(opts: {
  role?: Role
  withSecondProperty?: boolean
  secondRole?: Role
  departmentId?: string | null
  departmentType?: DepartmentType | null
  prefs?: Record<string, unknown>
} = {}): SessionOut {
  const memberships: MembershipOut[] = [
    {
      propertyId: 'prop-a',
      propertyName: 'Harbourview Hotel',
      propertyCode: 'HVH',
      role: opts.role ?? 'agent',
      departmentId: opts.departmentId ?? null,
      departmentType: opts.departmentType ?? null,
    },
  ]
  if (opts.withSecondProperty) {
    memberships.push({
      propertyId: 'prop-b',
      propertyName: 'Lakeside Inn',
      propertyCode: 'LSI',
      role: opts.secondRole ?? opts.role ?? 'agent',
      departmentId: null,
      departmentType: null,
    })
  }
  return {
    user: {
      id: 'u-ava',
      email: 'ava@hvh.test',
      firstName: 'Ava',
      lastName: 'Nolan',
      locale: 'en',
      avatarUrl: null,
      notificationPrefs: opts.prefs ?? {},
    },
    memberships,
  }
}

export function testQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  })
}

export function renderWithProviders(
  ui: ReactNode,
  opts: { session?: SessionOut; route?: string; client?: QueryClient } = {},
): RenderResult & { client: QueryClient } {
  const client = opts.client ?? testQueryClient()
  if (opts.session) client.setQueryData(qk.session, opts.session)
  const result = render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[opts.route ?? '/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        {ui}
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...result, client }
}
