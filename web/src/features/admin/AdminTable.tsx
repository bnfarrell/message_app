import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'

export type Column<T> = { key: string; head: string; render: (row: T) => ReactNode; mono?: boolean }

export function AdminTable<T extends { id: string }>({
  columns,
  rows,
  selectedId,
  onSelect,
}: {
  columns: Column<T>[]
  rows: T[]
  selectedId: string | null
  onSelect: (row: T) => void
}) {
  return (
    <table className="w-full">
      <thead>
        <tr>
          {columns.map((column) => (
            <th
              key={column.key}
              className="border-b border-border2 px-3.5 py-2.5 text-left text-[11.5px] font-bold uppercase tracking-wider text-text3"
            >
              {column.head}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={row.id}
            tabIndex={0}
            aria-selected={row.id === selectedId}
            onClick={() => onSelect(row)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onSelect(row)
              }
            }}
            className={cn('cursor-pointer', row.id === selectedId ? 'bg-sel' : 'hover:bg-surface2')}
          >
            {columns.map((column) => (
              <td
                key={column.key}
                className={cn(
                  'border-b border-border px-3.5 py-3 align-top text-[13.5px]',
                  column.mono && 'font-mono',
                )}
              >
                {column.render(row)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
