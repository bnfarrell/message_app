import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Avatar } from './Avatar'

describe('Avatar', () => {
  it('shows two initials for a full name', () => {
    render(<Avatar name="Sarah Chen" />)
    expect(screen.getByText('SC')).toBeInTheDocument()
  })

  it('shows one initial for a single name', () => {
    render(<Avatar name="Ava" />)
    expect(screen.getByText('A')).toBeInTheDocument()
  })

  it('falls back to ? for an empty name rather than rendering blank', () => {
    render(<Avatar name="   " />)
    expect(screen.getByText('?')).toBeInTheDocument()
  })

  it('exposes the full name to assistive tech', () => {
    render(<Avatar name="Marcus Reyes" />)
    expect(screen.getByTitle('Marcus Reyes')).toBeInTheDocument()
  })
})
