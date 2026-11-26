import { z } from 'zod'

export const PASSWORD_RULES = {
  MIN_LENGTH: 8,
  MAX_LENGTH: 128,
  PATTERNS: {
    lowercase: /[a-z]/,
    uppercase: /[A-Z]/,
    digit: /\d/,
    special: /[!@#$%^&*()_+\-=[\]{}|;:,.<>?]/,
  },
} as const

export interface PasswordRequirement {
  id: string
  test: (password: string) => boolean
  translationKey: string
}

export const PASSWORD_REQUIREMENTS: PasswordRequirement[] = [
  {
    id: 'minLength',
    test: (pwd) => pwd.length >= PASSWORD_RULES.MIN_LENGTH,
    translationKey: 'auth:passwordRequirements.minLength',
  },
  {
    id: 'lowercase',
    test: (pwd) => PASSWORD_RULES.PATTERNS.lowercase.test(pwd),
    translationKey: 'auth:passwordRequirements.lowercase',
  },
  {
    id: 'uppercase',
    test: (pwd) => PASSWORD_RULES.PATTERNS.uppercase.test(pwd),
    translationKey: 'auth:passwordRequirements.uppercase',
  },
  {
    id: 'digit',
    test: (pwd) => PASSWORD_RULES.PATTERNS.digit.test(pwd),
    translationKey: 'auth:passwordRequirements.digit',
  },
  {
    id: 'special',
    test: (pwd) => PASSWORD_RULES.PATTERNS.special.test(pwd),
    translationKey: 'auth:passwordRequirements.special',
  },
]

/**
 * Creates a Zod password schema with i18n validation messages.
 * Use this in forms to ensure consistent password validation.
 */
export const createPasswordSchema = (t: (key: string) => string) => {
  return z
    .string()
    .min(PASSWORD_RULES.MIN_LENGTH, t('auth:validation.passwordMin'))
    .max(PASSWORD_RULES.MAX_LENGTH, t('auth:validation.passwordMax'))
    .regex(PASSWORD_RULES.PATTERNS.lowercase, t('auth:validation.passwordLowercase'))
    .regex(PASSWORD_RULES.PATTERNS.uppercase, t('auth:validation.passwordUppercase'))
    .regex(PASSWORD_RULES.PATTERNS.digit, t('auth:validation.passwordNumber'))
    .regex(PASSWORD_RULES.PATTERNS.special, t('auth:validation.passwordSpecial'))
}
