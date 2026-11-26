import { beforeEach, describe, expect, it, vi } from 'vitest'

// The breadcrumb buffer is module-level state, so reset modules before each
// test to get a fresh, isolated buffer.
let mod: typeof import('./errorBreadcrumbs')

beforeEach(async () => {
  vi.resetModules()
  document.body.innerHTML = ''
  mod = await import('./errorBreadcrumbs')
})

describe('recordBreadcrumb', () => {
  it('records breadcrumbs in order (oldest first)', () => {
    mod.recordBreadcrumb('navigation', 'Navigated to /a')
    mod.recordBreadcrumb('click', 'Clicked "Save"')

    const crumbs = mod.getBreadcrumbs()
    expect(crumbs.map((c) => c.label)).toEqual(['Navigated to /a', 'Clicked "Save"'])
    expect(crumbs.map((c) => c.type)).toEqual(['navigation', 'click'])
    expect(crumbs[0].timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/)
  })

  it('ignores empty and whitespace-only labels', () => {
    mod.recordBreadcrumb('click', '')
    mod.recordBreadcrumb('click', '   ')
    expect(mod.getBreadcrumbs()).toHaveLength(0)
  })

  it('trims and collapses internal whitespace', () => {
    mod.recordBreadcrumb('click', '  Save\n  changes  ')
    expect(mod.getBreadcrumbs()[0].label).toBe('Save changes')
  })

  it('caps label length at 100 characters', () => {
    mod.recordBreadcrumb('click', 'x'.repeat(250))
    expect(mod.getBreadcrumbs()[0].label).toHaveLength(100)
  })

  it('caps the buffer at 15 entries, evicting oldest', () => {
    for (let i = 0; i < 20; i++) {
      mod.recordBreadcrumb('navigation', `nav-${i}`)
    }
    const crumbs = mod.getBreadcrumbs()
    expect(crumbs).toHaveLength(15)
    expect(crumbs[0].label).toBe('nav-5')
    expect(crumbs[14].label).toBe('nav-19')
  })

  it('returns a defensive copy from getBreadcrumbs', () => {
    mod.recordBreadcrumb('navigation', 'nav')
    const first = mod.getBreadcrumbs()
    first.push({ type: 'click', label: 'mutated', timestamp: 'x' })
    expect(mod.getBreadcrumbs()).toHaveLength(1)
  })
})

describe('installBreadcrumbCollectors', () => {
  it('records a click breadcrumb using the element text label', () => {
    mod.installBreadcrumbCollectors()
    const button = document.createElement('button')
    button.textContent = 'Save changes'
    document.body.appendChild(button)

    button.dispatchEvent(new MouseEvent('click', { bubbles: true }))

    const crumbs = mod.getBreadcrumbs()
    expect(crumbs).toHaveLength(1)
    expect(crumbs[0]).toMatchObject({ type: 'click', label: 'Clicked "Save changes"' })
  })

  it('prefers data-breadcrumb, then aria-label, over text content', () => {
    mod.installBreadcrumbCollectors()

    const dataEl = document.createElement('button')
    dataEl.setAttribute('data-breadcrumb', 'Custom label')
    dataEl.textContent = 'ignored text'
    document.body.appendChild(dataEl)
    dataEl.dispatchEvent(new MouseEvent('click', { bubbles: true }))

    const ariaEl = document.createElement('button')
    ariaEl.setAttribute('aria-label', 'Aria label')
    ariaEl.textContent = 'ignored text'
    document.body.appendChild(ariaEl)
    ariaEl.dispatchEvent(new MouseEvent('click', { bubbles: true }))

    expect(mod.getBreadcrumbs().map((c) => c.label)).toEqual([
      'Clicked "Custom label"',
      'Clicked "Aria label"',
    ])
  })

  it('resolves clicks on descendants up to the nearest interactive element', () => {
    mod.installBreadcrumbCollectors()
    const button = document.createElement('button')
    button.setAttribute('aria-label', 'Delete')
    const icon = document.createElement('span')
    button.appendChild(icon)
    document.body.appendChild(button)

    icon.dispatchEvent(new MouseEvent('click', { bubbles: true }))

    expect(mod.getBreadcrumbs()[0].label).toBe('Clicked "Delete"')
  })

  it('ignores clicks that are not on an interactive element', () => {
    mod.installBreadcrumbCollectors()
    const div = document.createElement('div')
    div.textContent = 'not interactive'
    document.body.appendChild(div)

    div.dispatchEvent(new MouseEvent('click', { bubbles: true }))

    expect(mod.getBreadcrumbs()).toHaveLength(0)
  })

  it('is idempotent: calling twice attaches a single listener', () => {
    mod.installBreadcrumbCollectors()
    mod.installBreadcrumbCollectors()
    const button = document.createElement('button')
    button.textContent = 'Once'
    document.body.appendChild(button)

    button.dispatchEvent(new MouseEvent('click', { bubbles: true }))

    expect(mod.getBreadcrumbs()).toHaveLength(1)
  })
})
