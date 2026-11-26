import type { NotificationWindowRule } from '@/types/site'

/** Backend limit (site_config.MAX_NOTIFICATION_RULES). */
export const MAX_NOTIFICATION_RULES = 20

/** ISO weekdays, Monday first. */
export const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7] as const

const TIME_RE = /^([01]\d|2[0-3]):([0-5]\d)$/

export type RuleErrorCode = 'noWeekdays' | 'invalidTime' | 'startNotBeforeEnd'

/** The default window: Mon-Fri 06:00-10:00 (functional description 15 Q4). */
export function defaultRule(): NotificationWindowRule {
  return { weekdays: [1, 2, 3, 4, 5], start: '06:00', end: '10:00' }
}

export function isValidTime(value: string): boolean {
  return TIME_RE.test(value)
}

/**
 * Validate one rule. Returns an error code or null. "HH:MM" strings compare
 * correctly as text, so `start >= end` also rejects an overnight span.
 */
export function validateRule(rule: NotificationWindowRule): RuleErrorCode | null {
  if (
    rule.weekdays.length === 0 ||
    !rule.weekdays.every((d) => Number.isInteger(d) && d >= 1 && d <= 7)
  ) {
    return 'noWeekdays'
  }
  if (!isValidTime(rule.start) || !isValidTime(rule.end)) return 'invalidTime'
  if (rule.start >= rule.end) return 'startNotBeforeEnd'
  return null
}

export type WindowErrorCode = 'tooManyRules'

export interface WindowValidation {
  /** One entry per rule, null when the rule is valid. */
  rules: Array<RuleErrorCode | null>
  list: WindowErrorCode | null
  valid: boolean
}

/** Validate the whole window. An empty list is valid and means "any time". */
export function validateWindow(rules: NotificationWindowRule[]): WindowValidation {
  const perRule = rules.map(validateRule)
  const list = rules.length > MAX_NOTIFICATION_RULES ? 'tooManyRules' : null
  return { rules: perRule, list, valid: list === null && perRule.every((e) => e === null) }
}

/** Add or remove a weekday; the result stays sorted and de-duplicated. */
export function toggleWeekday(
  rule: NotificationWindowRule,
  day: number
): NotificationWindowRule {
  const has = rule.weekdays.includes(day)
  const weekdays = has ? rule.weekdays.filter((d) => d !== day) : [...rule.weekdays, day]
  return { ...rule, weekdays: [...new Set(weekdays)].sort((a, b) => a - b) }
}

export function addRule(rules: NotificationWindowRule[]): NotificationWindowRule[] {
  return [...rules, defaultRule()]
}

export function removeRule(
  rules: NotificationWindowRule[],
  index: number
): NotificationWindowRule[] {
  return rules.filter((_, i) => i !== index)
}

export function updateRule(
  rules: NotificationWindowRule[],
  index: number,
  patch: Partial<NotificationWindowRule>
): NotificationWindowRule[] {
  return rules.map((rule, i) => (i === index ? { ...rule, ...patch } : rule))
}

/** Normalised copy for sending to the API (sorted unique weekdays). */
export function normaliseWindow(rules: NotificationWindowRule[]): NotificationWindowRule[] {
  return rules.map((rule) => ({
    weekdays: [...new Set(rule.weekdays)].sort((a, b) => a - b),
    start: rule.start,
    end: rule.end,
  }))
}
