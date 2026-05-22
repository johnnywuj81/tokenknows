/**
 * App.tsx · Bootstrap smoke component.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'


describe('App', () => {
  it('renders bootstrap title', () => {
    render(<App />)
    expect(screen.getByText(/Bootstrap OK/)).toBeInTheDocument()
  })

  it('renders 3 status badges', () => {
    render(<App />)
    expect(screen.getByText('success')).toBeInTheDocument()
    expect(screen.getByText('warning')).toBeInTheDocument()
    expect(screen.getByText('danger')).toBeInTheDocument()
  })

  it('renders CTA button', () => {
    render(<App />)
    expect(screen.getByText(/主 CTA/)).toBeInTheDocument()
  })
})
