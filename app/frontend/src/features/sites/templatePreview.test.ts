import { describe, it, expect } from 'vitest'
import {
  extractPlaceholders,
  findUnknownPlaceholders,
  insertPlaceholder,
  isTemplateChanged,
  renderPreview,
  sampleValues,
} from './templatePreview'

const allowedInitial = ['occupancyPct', 'site', 'topZones', 'zone']

describe('template placeholders', () => {
  it('extracts unique placeholders in order', () => {
    expect(extractPlaceholders('{site}: {zone} and {site} {occupancyPct}')).toEqual([
      'site',
      'zone',
      'occupancyPct',
    ])
    expect(extractPlaceholders('no placeholders { site } {1bad} {}')).toEqual([])
  })

  it('flags placeholders the type does not provide (BF-70)', () => {
    expect(findUnknownPlaceholders('{site} {fullZone}', allowedInitial)).toEqual(['fullZone'])
    expect(findUnknownPlaceholders('{site} {typo}', allowedInitial)).toEqual(['typo'])
    expect(findUnknownPlaceholders('{site}', allowedInitial)).toEqual([])
  })
})

describe('preview rendering', () => {
  const samples = sampleValues('Alice Lane')

  it('fills known placeholders with sample values and the real site name', () => {
    expect(renderPreview('{site}: {topZones} at {occupancyPct}%', samples)).toBe(
      'Alice Lane: Basement 3 and Basement 4 at 92%'
    )
  })

  it('leaves unknown or disallowed placeholders as written', () => {
    expect(renderPreview('{site} {nope}', samples)).toBe('Alice Lane {nope}')
    expect(renderPreview('{fullZone} is full', samples, allowedInitial)).toBe('{fullZone} is full')
    expect(renderPreview('{fullZone} is full', samples, [...allowedInitial, 'fullZone'])).toBe(
      'Basement 1 is full'
    )
  })

  it('does not treat prototype names as samples', () => {
    expect(renderPreview('{constructor}', samples)).toBe('{constructor}')
  })
})

describe('placeholder insertion', () => {
  it('inserts at the cursor and returns the new cursor position', () => {
    expect(insertPlaceholder('Hello ', 6, 6, 'site')).toEqual({ text: 'Hello {site}', cursor: 12 })
  })

  it('replaces the selection', () => {
    expect(insertPlaceholder('a XXX b', 2, 5, 'zone')).toEqual({ text: 'a {zone} b', cursor: 8 })
  })

  it('clamps an out-of-range selection', () => {
    expect(insertPlaceholder('ab', 10, 20, 'site').text).toBe('ab{site}')
  })
})

describe('change detection', () => {
  it('detects edits', () => {
    const saved = { title: 'T', body: 'B' }
    expect(isTemplateChanged(saved, saved)).toBe(false)
    expect(isTemplateChanged({ title: 'T', body: 'B2' }, saved)).toBe(true)
  })
})
