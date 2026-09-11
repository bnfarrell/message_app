import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BarChart } from './BarChart'

const BUCKETS = [
  { hour: 0, count: 2 },
  { hour: 1, count: 0 },
  { hour: 18, count: 31 },
  { hour: 19, count: 14 },
]

describe('BarChart', () => {
  it('renders one bar per bucket', () => {
    render(<BarChart buckets={BUCKETS} labelOf={(b) => `${b.hour}:00`} />)
    expect(screen.getAllByTestId('bar')).toHaveLength(4)
  })

  it('scales the tallest bar to full height', () => {
    render(<BarChart buckets={BUCKETS} labelOf={(b) => `${b.hour}:00`} />)
    const bars = screen.getAllByTestId('bar')
    expect(bars[2]!.style.height).toBe('100%')
  })

  it('scales the others proportionally', () => {
    render(<BarChart buckets={BUCKETS} labelOf={(b) => `${b.hour}:00`} />)
    // 14 of 31 ≈ 45.2%
    expect(parseFloat(screen.getAllByTestId('bar')[3]!.style.height)).toBeCloseTo(45.2, 0)
  })

  it('gives a zero bucket zero height without dividing by anything', () => {
    render(<BarChart buckets={BUCKETS} labelOf={(b) => `${b.hour}:00`} />)
    expect(screen.getAllByTestId('bar')[1]!.style.height).toBe('0%')
  })

  it('survives an all-zero series rather than rendering NaN', () => {
    render(
      <BarChart buckets={[{ hour: 0, count: 0 }, { hour: 1, count: 0 }]} labelOf={(b) => `${b.hour}`} />,
    )
    for (const bar of screen.getAllByTestId('bar')) expect(bar.style.height).toBe('0%')
  })

  it('renders nothing for an empty series', () => {
    const { container } = render(<BarChart buckets={[]} labelOf={() => ''} />)
    expect(container.querySelectorAll('[data-testid="bar"]')).toHaveLength(0)
  })

  it('labels each bar for assistive tech and hover', () => {
    render(<BarChart buckets={BUCKETS} labelOf={(b) => `${b.hour}:00 · ${b.count} messages`} />)
    expect(screen.getByTitle('18:00 · 31 messages')).toBeInTheDocument()
  })

  it('paints a highlighted bar in danger, the only red allowed', () => {
    render(
      <BarChart
        buckets={BUCKETS}
        labelOf={(b) => `${b.hour}`}
        highlightOf={(b) => b.hour === 19}
      />,
    )
    const bars = screen.getAllByTestId('bar')
    expect(bars[3]!.className).toContain('bg-danger')
    expect(bars[2]!.className).toContain('bg-accent')
  })
})
