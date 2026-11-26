import { z } from 'zod'
import { validateRule, MAX_NOTIFICATION_RULES } from './notificationWindow'

/** Backend: STALE_LIMIT_MIN_S = 2 x ParkIT's 60 s post interval. */
export const STALE_LIMIT_MIN_S = 120

export type Translate = (key: string, options?: Record<string, unknown>) => string

/** Valid IANA name? Browsers throw a RangeError for an unknown zone. */
export function isValidTimeZone(name: string): boolean {
  if (!name || name.length > 64) return false
  try {
    new Intl.DateTimeFormat('en', { timeZone: name })
    return true
  } catch {
    return false
  }
}

/** Default settings (functional description 10.1). */
export const SITE_SETTINGS_DEFAULTS = {
  trigger_pct: 90,
  reset_pct: 80,
  change_points: 5,
  change_direction: 'RISING' as const,
  stabilisation_s: 300,
  recommendation_margin: 10,
  stale_limit_s: 120,
  partial_is_stale: true,
  recovery_push: false,
  zone_advisory: false,
  zone_reset_gap: 10,
  notification_window: [{ weekdays: [1, 2, 3, 4, 5], start: '06:00', end: '10:00' }],
  cooldown_s: 1800,
  daily_cap: 2,
  push_expiry_s: 1800,
}

const int = (t: Translate, min: number, max?: number) => {
  let schema = z
    .number({ error: t('sites:validation.integer') })
    .int(t('sites:validation.integer'))
    .min(min, t('sites:validation.min', { min }))
  if (max !== undefined) schema = schema.max(max, t('sites:validation.max', { max }))
  return schema
}

/**
 * Zod schema for the site settings form (BF-71, section 10.1). Mirrors the
 * backend's `validate_site_config`: an invalid value is refused, never clamped.
 * `t` supplies the messages so the schema can be built with the page's
 * translator (and with an identity function in tests).
 */
export function createSiteSettingsSchema(t: Translate) {
  return z
    .object({
      trigger_pct: int(t, 1, 100),
      reset_pct: int(t, 0),
      change_points: int(t, 1, 50),
      change_direction: z.enum(['RISING', 'BOTH']),
      stabilisation_s: int(t, 0, 3600),
      recommendation_margin: int(t, 0),
      stale_limit_s: int(t, STALE_LIMIT_MIN_S),
      partial_is_stale: z.boolean(),
      recovery_push: z.boolean(),
      zone_advisory: z.boolean(),
      zone_reset_gap: int(t, 1, 50),
      notification_window: z
        .array(
          z.object({
            weekdays: z.array(z.number().int()),
            start: z.string(),
            end: z.string(),
          })
        )
        .max(MAX_NOTIFICATION_RULES, t('sites:validation.tooManyRules', { max: MAX_NOTIFICATION_RULES }))
        .superRefine((rules, ctx) => {
          rules.forEach((rule, index) => {
            const code = validateRule(rule)
            if (code) {
              ctx.addIssue({
                code: 'custom',
                path: [index],
                message: t(`sites:validation.window.${code}`),
              })
            }
          })
        }),
      cooldown_s: int(t, 0),
      daily_cap: int(t, 0),
      push_expiry_s: int(t, 60, 86400),
    })
    .superRefine((data, ctx) => {
      if (
        Number.isFinite(data.reset_pct) &&
        Number.isFinite(data.trigger_pct) &&
        data.reset_pct >= data.trigger_pct
      ) {
        ctx.addIssue({
          code: 'custom',
          path: ['reset_pct'],
          message: t('sites:validation.resetBelowTrigger'),
        })
      }
    })
}

export type SiteSettingsFormValues = z.infer<ReturnType<typeof createSiteSettingsSchema>>

/** Site details / identity form (overview tab). */
export function createSiteIdentitySchema(t: Translate) {
  return z.object({
    name: z
      .string()
      .trim()
      .min(1, t('sites:validation.required'))
      .max(255, t('sites:validation.maxLength', { max: 255 })),
    fcm_topic: z
      .string()
      .max(255, t('sites:validation.maxLength', { max: 255 }))
      .regex(/^[a-zA-Z0-9\-_.~%]*$/, t('sites:validation.topic')),
    time_zone: z.string().refine(isValidTimeZone, t('sites:validation.timeZone')),
  })
}
export type SiteIdentityFormValues = z.infer<ReturnType<typeof createSiteIdentitySchema>>

/** Same pattern as the backend SLUG_PATTERN. */
export const SLUG_PATTERN = /^[a-z0-9][a-z0-9_-]{0,63}$/

export function createSiteCreateSchema(t: Translate) {
  return z.object({
    slug: z.string().regex(SLUG_PATTERN, t('sites:validation.slug')),
    name: z
      .string()
      .trim()
      .min(1, t('sites:validation.required'))
      .max(255, t('sites:validation.maxLength', { max: 255 })),
    time_zone: z.string().refine((v) => v === '' || isValidTimeZone(v), t('sites:validation.timeZone')),
    fcm_topic: z
      .string()
      .max(255, t('sites:validation.maxLength', { max: 255 }))
      .regex(/^[a-zA-Z0-9\-_.~%]*$/, t('sites:validation.topic')),
    organization_id: z.string(),
  })
}
export type SiteCreateFormValues = z.infer<ReturnType<typeof createSiteCreateSchema>>

/** Zone settings (section 10.2), mirrors `validate_zone_settings`. */
export function createZoneSchema(t: Translate, mode: 'create' | 'edit') {
  return z
    .object({
      slug:
        mode === 'create'
          ? z.string().regex(SLUG_PATTERN, t('sites:validation.slug'))
          : z.string(),
      name: z
        .string()
        .trim()
        .min(1, t('sites:validation.required'))
        .max(255, t('sites:validation.maxLength', { max: 255 })),
      display_order: int(t, 0, 100000),
      enabled: z.boolean(),
      recommendable: z.boolean(),
      preferred: z.boolean(),
      priority: int(t, 0, 100000),
      limited_pct: int(t, 1, 100),
      full_pct: int(t, 1, 100),
      full_min_free: int(t, 0),
      unknown_limit_pct: int(t, 0, 100),
      /** undefined = no zone advisory */
      advisory_pct: int(t, 1, 100).optional(),
      note: z.string().max(2000, t('sites:validation.maxLength', { max: 2000 })),
    })
    .superRefine((data, ctx) => {
      if (data.limited_pct > data.full_pct) {
        ctx.addIssue({
          code: 'custom',
          path: ['limited_pct'],
          message: t('sites:validation.limitedBelowFull'),
        })
      }
    })
}
export type ZoneFormValues = z.infer<ReturnType<typeof createZoneSchema>>
