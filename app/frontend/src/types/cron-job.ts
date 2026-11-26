/**
 * Cron Job types - TypeScript types matching backend serializers
 */

/**
 * Cron job execution status
 */
export type CronJobStatus = 'pending' | 'running' | 'success' | 'error'

/**
 * Single cron job definition response
 */
export interface CronJob {
  id: string
  organization_id: string | null
  name: string
  description: string | null
  code: string
  schedule_expression: string
  is_active: boolean
  is_enabled_by_default_for_new_orgs: boolean
  parameters: Record<string, unknown> | null
  last_run_time: string | null
  next_run_time: string | null
  last_run_status: CronJobStatus
  last_run_error_message: string | null
  created_time: string | null
  updated_time: string | null
  is_platform_wide: boolean
  // Execution stats (last 24 hours)
  executions_24h?: number
  failures_24h?: number
  failure_rate?: number
  avg_duration_ms?: number | null
}

/**
 * Request schema for creating a cron job
 */
export interface CreateCronJobRequest {
  name: string
  description?: string | null
  code: string
  schedule_expression: string
  is_active?: boolean
  is_enabled_by_default_for_new_orgs?: boolean
  parameters?: Record<string, unknown> | null
  is_platform_wide?: boolean
}

/**
 * Request schema for updating a cron job
 */
export interface UpdateCronJobRequest {
  name?: string
  description?: string | null
  schedule_expression?: string
  is_active?: boolean
  is_enabled_by_default_for_new_orgs?: boolean
  parameters?: Record<string, unknown> | null
}

/**
 * Paginated list response for cron jobs
 */
export interface CronJobListResponse {
  items: CronJob[]
  total: number
  limit: number
  offset: number
}

/**
 * Query parameters for listing cron jobs
 */
export interface CronJobListParams {
  is_active?: boolean
  organization_id?: string
  limit?: number
  offset?: number
}

/**
 * Single cron job execution response
 */
export interface CronJobExecution {
  id: string
  cron_job_id: string
  organization_id: string | null
  started_at: string
  completed_at: string | null
  status: CronJobStatus
  result: Record<string, unknown> | null
  error_message: string | null
  created_time: string | null
}

/**
 * Paginated list response for cron job executions
 */
export interface CronJobExecutionListResponse {
  items: CronJobExecution[]
  total: number
  limit: number
  offset: number
}

/**
 * Query parameters for listing cron job executions
 */
export interface CronJobExecutionListParams {
  limit?: number
  offset?: number
}

/**
 * Request schema for toggling cron job active status
 */
export interface ToggleCronJobRequest {
  is_active: boolean
}

/**
 * Response for manually triggering a cron job
 */
export interface TriggerCronJobResponse {
  message: string
  message_code: string
  execution_id: string
}

/**
 * Response for deleting a cron job
 */
export interface DeleteCronJobResponse {
  message: string
  message_code: string
}

/**
 * Single config key associated with a cron job
 */
export interface CronJobConfigKey {
  key: string
  value_type: 'integer' | 'string' | 'boolean' | 'float'
  default: unknown
  current_value: unknown
  label: string
  description: string
  min_value?: number | null
  max_value?: number | null
}

/**
 * Response for cron job configuration
 */
export interface CronJobConfigResponse {
  job_code: string
  has_config: boolean
  config_keys: CronJobConfigKey[]
}

/**
 * Request schema for updating a cron job config value
 */
export interface UpdateCronJobConfigRequest {
  key: string
  value: string
}
