/**
 * UpdateBanner: only renders once a new build is staged and ready, applies it
 * on the CTA, and stays gone once dismissed.
 *
 * react-i18next is mocked globally (src/test/setup.ts) so `t` returns the key.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const applyUpdate = vi.fn()
const dismissUpdate = vi.fn()
let updateReady = false

vi.mock('@/hooks/useAppUpdate', () => ({
  useAppUpdate: () => ({
    updateReady,
    staged: updateReady,
    serverVersion: null,
    applyUpdate,
    dismissUpdate,
  }),
}))

// The policy has its own tests; here it must simply not fire during a render.
vi.mock('@/hooks/useAutoApplyUpdate', () => ({ useAutoApplyUpdate: () => {} }))

import { UpdateBanner } from './UpdateBanner'

describe('UpdateBanner', () => {
  beforeEach(() => {
    cleanup()
    applyUpdate.mockClear()
    dismissUpdate.mockClear()
    updateReady = false
  })

  it('renders nothing while the build is current', () => {
    const { container } = render(<UpdateBanner />)
    expect(container).toBeEmptyDOMElement()
  })

  it('announces the update as a polite status card', () => {
    updateReady = true
    render(<UpdateBanner />)
    const card = screen.getByRole('status')
    expect(card).toHaveAttribute('aria-live', 'polite')
    expect(screen.getByText('updatePrompt.title')).toBeInTheDocument()
    expect(screen.getByText('updatePrompt.message')).toBeInTheDocument()
  })

  it('applies the staged update on the primary CTA', async () => {
    updateReady = true
    render(<UpdateBanner />)
    await userEvent.click(screen.getByRole('button', { name: 'updatePrompt.apply' }))
    expect(applyUpdate).toHaveBeenCalledTimes(1)
  })

  it('stays hidden after "Later", and remembers the dismissal', async () => {
    updateReady = true
    render(<UpdateBanner />)
    await userEvent.click(screen.getByRole('button', { name: 'updatePrompt.later' }))
    expect(screen.queryByRole('status')).toBeNull()
    expect(applyUpdate).not.toHaveBeenCalled()
    // Persisted per deployed commit, so "not now" is not "again in five minutes".
    expect(dismissUpdate).toHaveBeenCalledTimes(1)
  })

  it('stays hidden after the close button', async () => {
    updateReady = true
    render(<UpdateBanner />)
    await userEvent.click(screen.getByRole('button', { name: 'updatePrompt.dismiss' }))
    expect(screen.queryByRole('status')).toBeNull()
    expect(dismissUpdate).toHaveBeenCalledTimes(1)
  })
})
