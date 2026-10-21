import { render, screen } from '@testing-library/react'
import { Building2 } from 'lucide-react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { Button } from '@/components/ui/button'

describe('Button', () => {
  it('slots a single element child when asChild is set', () => {
    render(
      <MemoryRouter>
        <Button asChild size="sm">
          <a href="/workspace/new">
            <Building2 aria-hidden="true" />
            New workspace
          </a>
        </Button>
      </MemoryRouter>,
    )

    const link = screen.getByRole('link', { name: 'New workspace' })
    expect(link).toHaveAttribute('href', '/workspace/new')
    expect(link.className).toContain('inline-flex')
    expect(link).not.toHaveAttribute('disabled')
  })

  it('renders children and a loading indicator for a plain button', () => {
    render(<Button loading>Save</Button>)

    const button = screen.getByRole('button', { name: 'Save' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
    expect(button.querySelector('.animate-spin')).not.toBeNull()
  })

  it('rejects loading combined with asChild instead of rendering an invalid slot', () => {
    expect(() =>
      render(
        <Button asChild loading>
          <a href="/">Home</a>
        </Button>,
      ),
    ).toThrow(/does not support `loading` together with `asChild`/)
  })
})
