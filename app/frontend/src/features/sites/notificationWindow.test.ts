import { describe, it, expect } from 'vitest'
import {
  MAX_NOTIFICATION_RULES,
  addRule,
  defaultRule,
  normaliseWindow,
  removeRule,
  toggleWeekday,
  updateRule,
  validateRule,
  validateWindow,
} from './notificationWindow'

describe('notification window logic', () => {
  it('default rule is Mon-Fri 06:00-10:00 and valid', () => {
    expect(defaultRule()).toEqual({ weekdays: [1, 2, 3, 4, 5], start: '06:00', end: '10:00' })
    expect(validateRule(defaultRule())).toBeNull()
  })

  it('requires start before end and refuses overnight spans', () => {
    expect(validateRule({ weekdays: [1], start: '10:00', end: '10:00' })).toBe('startNotBeforeEnd')
    expect(validateRule({ weekdays: [1], start: '22:00', end: '02:00' })).toBe('startNotBeforeEnd')
    expect(validateRule({ weekdays: [1], start: '00:00', end: '23:59' })).toBeNull()
  })

  it('requires at least one valid weekday', () => {
    expect(validateRule({ weekdays: [], start: '06:00', end: '10:00' })).toBe('noWeekdays')
    expect(validateRule({ weekdays: [0], start: '06:00', end: '10:00' })).toBe('noWeekdays')
    expect(validateRule({ weekdays: [8], start: '06:00', end: '10:00' })).toBe('noWeekdays')
  })

  it('refuses malformed times', () => {
    expect(validateRule({ weekdays: [1], start: '', end: '10:00' })).toBe('invalidTime')
    expect(validateRule({ weekdays: [1], start: '6:00', end: '10:00' })).toBe('invalidTime')
    expect(validateRule({ weekdays: [1], start: '06:00', end: '24:00' })).toBe('invalidTime')
  })

  it('treats an empty list as valid (any time)', () => {
    expect(validateWindow([])).toEqual({ rules: [], list: null, valid: true })
  })

  it('reports errors per rule and an over-long list', () => {
    const bad = { weekdays: [], start: '06:00', end: '10:00' }
    const result = validateWindow([defaultRule(), bad])
    expect(result.rules).toEqual([null, 'noWeekdays'])
    expect(result.valid).toBe(false)
    const many = validateWindow(Array(MAX_NOTIFICATION_RULES + 1).fill(defaultRule()))
    expect(many.list).toBe('tooManyRules')
    expect(many.valid).toBe(false)
  })

  it('toggles weekdays keeping them sorted and unique', () => {
    const rule = { weekdays: [1, 3], start: '06:00', end: '10:00' }
    expect(toggleWeekday(rule, 2).weekdays).toEqual([1, 2, 3])
    expect(toggleWeekday(rule, 3).weekdays).toEqual([1])
    expect(rule.weekdays).toEqual([1, 3])
  })

  it('adds, updates and removes rules immutably', () => {
    const start = [defaultRule()]
    const added = addRule(start)
    expect(added).toHaveLength(2)
    expect(start).toHaveLength(1)
    const updated = updateRule(added, 1, { start: '07:00' })
    expect(updated[1].start).toBe('07:00')
    expect(updated[0].start).toBe('06:00')
    expect(removeRule(updated, 0)).toEqual([updated[1]])
  })

  it('normalises weekdays for the API', () => {
    expect(normaliseWindow([{ weekdays: [3, 1, 3], start: '06:00', end: '10:00' }])).toEqual([
      { weekdays: [1, 3], start: '06:00', end: '10:00' },
    ])
  })
})
