import { useCallback, useState, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useDropzone } from 'react-dropzone'
import { Upload, X, FileText, Image, File as FileIcon, Loader2 } from 'lucide-react'
import { parse as parseDate } from 'date-fns'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { DatePicker } from '@/components/ui/date-picker'
import { MultiSelect } from '@/components/ui/multi-select'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { cn, formatBytes } from '@/lib/utils'

// Maximum size for submitted_data (100KB as per backend validation)
const MAX_SUBMITTED_DATA_SIZE = 102400
import { useSubmitOnboardingStepMutation, type OnboardingStep as OnboardingStepType } from '@/store/api/onboardingApi'
import { useUploadFileMutation, filesApi } from '@/features/files/filesApi'
import { useAppDispatch } from '@/store/hooks'

interface OnboardingStepProps {
  step: OnboardingStepType
  onComplete: () => void
  onBack?: () => void
  initialData?: Record<string, unknown>
  isLastStep?: boolean
}

interface SelectOption {
  value: string
  label: string
}

interface FieldConfig {
  type?: 'string' | 'email' | 'number' | 'url' | 'textarea' | 'select' | 'file' | 'checkbox' | 'date' | 'phone' | 'radio' | 'multiselect'
  label?: string
  description?: string
  placeholder?: string
  required?: boolean
  minLength?: number
  maxLength?: number
  min?: number
  max?: number
  pattern?: string
  rows?: number
  // Select/radio/multiselect field options
  options?: SelectOption[] | string[]
  // File field options
  accept?: string
  maxSize?: number
  // Checkbox options
  defaultChecked?: boolean
  // Date options
  minDate?: string
  maxDate?: string
  dateFormat?: string
  // Phone options
  phoneFormat?: string
  defaultCountry?: string
  // Radio options
  layout?: 'horizontal' | 'vertical'
  // Multiselect options
  maxSelections?: number
}

function buildZodSchema(
  requiredFields: Record<string, unknown>,
  t: (key: string, options?: Record<string, unknown>) => string
): z.ZodObject<Record<string, z.ZodTypeAny>> {
  const schemaFields: Record<string, z.ZodTypeAny> = {}

  Object.entries(requiredFields).forEach(([fieldName, fieldConfig]) => {
    const config = fieldConfig as FieldConfig
    const fieldType = config.type || 'string'
    let fieldSchema: z.ZodTypeAny

    switch (fieldType) {
      case 'email':
        fieldSchema = z.string().email(t('onboarding:validation.invalidEmail'))
        break
      case 'number':
        fieldSchema = z.coerce.number()
        if (config.min !== undefined) {
          fieldSchema = (fieldSchema as z.ZodNumber).min(config.min, t('onboarding:validation.minValue', { min: config.min }))
        }
        if (config.max !== undefined) {
          fieldSchema = (fieldSchema as z.ZodNumber).max(config.max, t('onboarding:validation.maxValue', { max: config.max }))
        }
        break
      case 'url':
        fieldSchema = z.string().url(t('onboarding:validation.invalidUrl'))
        break
      case 'textarea':
        fieldSchema = z.string()
        if (config.minLength) {
          fieldSchema = (fieldSchema as z.ZodString).min(config.minLength, t('onboarding:validation.minLength', { min: config.minLength }))
        }
        if (config.maxLength) {
          fieldSchema = (fieldSchema as z.ZodString).max(config.maxLength, t('onboarding:validation.maxLength', { max: config.maxLength }))
        }
        break
      case 'select':
        // Select stores a string value
        fieldSchema = z.string()
        break
      case 'file':
        // File stores the uploaded media ID as a string
        fieldSchema = z.string()
        break
      case 'checkbox':
        // Checkbox stores a boolean value
        fieldSchema = z.boolean()
        break
      case 'date':
        // Date stores an ISO date string
        fieldSchema = z.string()
        if (config.minDate) {
          const minDate = parseDate(config.minDate, 'yyyy-MM-dd', new Date())
          fieldSchema = (fieldSchema as z.ZodString).refine(
            (val) => !val || parseDate(val, 'yyyy-MM-dd', new Date()) >= minDate,
            { message: t('onboarding:validation.minDate', { date: config.minDate }) }
          )
        }
        if (config.maxDate) {
          const maxDate = parseDate(config.maxDate, 'yyyy-MM-dd', new Date())
          fieldSchema = (fieldSchema as z.ZodString).refine(
            (val) => !val || parseDate(val, 'yyyy-MM-dd', new Date()) <= maxDate,
            { message: t('onboarding:validation.maxDate', { date: config.maxDate }) }
          )
        }
        break
      case 'phone':
        // Phone stores a phone number string
        fieldSchema = z.string()
        break
      case 'radio':
        // Radio stores a string value
        fieldSchema = z.string()
        break
      case 'multiselect':
        // Multiselect stores an array of strings
        fieldSchema = z.array(z.string())
        if (config.maxSelections) {
          fieldSchema = (fieldSchema as z.ZodArray<z.ZodString>).max(
            config.maxSelections,
            t('onboarding:validation.maxSelections', { max: config.maxSelections })
          )
        }
        break
      default:
        fieldSchema = z.string()
        if (config.minLength) {
          fieldSchema = (fieldSchema as z.ZodString).min(config.minLength, t('onboarding:validation.minLength', { min: config.minLength }))
        }
        if (config.maxLength) {
          fieldSchema = (fieldSchema as z.ZodString).max(config.maxLength, t('onboarding:validation.maxLength', { max: config.maxLength }))
        }
        if (config.pattern) {
          fieldSchema = (fieldSchema as z.ZodString).regex(new RegExp(config.pattern), t('onboarding:validation.invalidFormat'))
        }
    }

    if (config.required !== false) {
      if (fieldType === 'string' || fieldType === 'textarea' || fieldType === 'select' || fieldType === 'file' || fieldType === 'date' || fieldType === 'phone' || fieldType === 'radio') {
        fieldSchema = (fieldSchema as z.ZodString).min(1, t('onboarding:validation.required'))
      } else if (fieldType === 'multiselect') {
        fieldSchema = (fieldSchema as z.ZodArray<z.ZodString>).min(1, t('onboarding:validation.required'))
      }
      // Checkbox and number don't need min(1) - they have valid default values
    } else {
      fieldSchema = fieldSchema.optional()
    }

    schemaFields[fieldName] = fieldSchema
  })

  return z.object(schemaFields)
}

function getDefaultValues(requiredFields: Record<string, unknown>, initialData?: Record<string, unknown>): Record<string, string | number | boolean | string[]> {
  const defaults: Record<string, string | number | boolean | string[]> = {}

  Object.entries(requiredFields).forEach(([fieldName, fieldConfig]) => {
    const config = fieldConfig as FieldConfig
    const fieldType = config.type || 'string'
    const initialValue = initialData?.[fieldName]

    if (fieldType === 'checkbox') {
      defaults[fieldName] = typeof initialValue === 'boolean' ? initialValue : (config.defaultChecked ?? false)
    } else if (fieldType === 'multiselect') {
      defaults[fieldName] = Array.isArray(initialValue) ? initialValue : []
    } else {
      defaults[fieldName] = (typeof initialValue === 'string' || typeof initialValue === 'number') ? initialValue : ''
    }
  })

  return defaults
}

// File upload state for tracking uploaded files per field
interface UploadedFile {
  mediaId: string
  fileName: string
  fileSize: number
}

export function OnboardingStep({ step, onComplete, onBack, initialData, isLastStep }: OnboardingStepProps) {
  const { t } = useTranslation(['onboarding', 'common'])
  const [submitStep, { isLoading }] = useSubmitOnboardingStepMutation()
  const [uploadFile, { isLoading: isUploading }] = useUploadFileMutation()
  const [uploadedFiles, setUploadedFiles] = useState<Record<string, UploadedFile>>({})
  const [uploadErrors, setUploadErrors] = useState<Record<string, string>>({})
  const [isLoadingFiles, setIsLoadingFiles] = useState(false)
  const dispatch = useAppDispatch()

  const schema = buildZodSchema(step.required_fields, t)
  const form = useForm({
    resolver: zodResolver(schema),
    defaultValues: getDefaultValues(step.required_fields, initialData),
  })

  // Load previously uploaded file info when editing a step with existing data
  useEffect(() => {
    const loadExistingFiles = async () => {
      if (!initialData) return

      // Find file fields with values in initialData
      const fileFieldsWithData: { fieldName: string; fileId: string }[] = []
      Object.entries(step.required_fields).forEach(([fieldName, fieldConfig]) => {
        const config = fieldConfig as FieldConfig
        if (config.type === 'file') {
          const fileId = initialData[fieldName]
          if (typeof fileId === 'string' && fileId.length > 0) {
            fileFieldsWithData.push({ fieldName, fileId })
          }
        }
      })

      if (fileFieldsWithData.length === 0) return

      setIsLoadingFiles(true)

      try {
        // Fetch file info for each file
        const results = await Promise.all(
          fileFieldsWithData.map(async ({ fieldName, fileId }) => {
            try {
              const result = await dispatch(
                filesApi.endpoints.getFile.initiate(fileId)
              ).unwrap()
              return {
                fieldName,
                fileInfo: {
                  mediaId: result.id,
                  fileName: result.original_filename || result.id,
                  fileSize: result.size_bytes || 0,
                },
              }
            } catch {
              // If file fetch fails, still show a placeholder
              return {
                fieldName,
                fileInfo: {
                  mediaId: fileId,
                  fileName: t('onboarding:fileUpload.previouslyUploaded'),
                  fileSize: 0,
                },
              }
            }
          })
        )

        // Update uploadedFiles state
        const filesMap: Record<string, UploadedFile> = {}
        results.forEach(({ fieldName, fileInfo }) => {
          filesMap[fieldName] = fileInfo
        })
        setUploadedFiles((prev) => ({ ...prev, ...filesMap }))
      } finally {
        setIsLoadingFiles(false)
      }
    }

    loadExistingFiles()
  }, [step.id, step.required_fields, initialData, dispatch, t])

  const onSubmit = async (data: Record<string, unknown>) => {
    try {
      // Validate data size before submission (100KB limit)
      const dataSize = new Blob([JSON.stringify(data)]).size
      if (dataSize > MAX_SUBMITTED_DATA_SIZE) {
        toast.error(t('onboarding:validation.dataTooLarge', { maxSize: formatBytes(MAX_SUBMITTED_DATA_SIZE) }))
        return
      }

      await submitStep({ stepId: step.id, data: { submitted_data: data } }).unwrap()
      toast.success(t('onboarding:stepCompleted'))
      onComplete()
    } catch (error) {
      const apiError = error as { data?: { detail?: string | object[] } }
      const errorMessage = typeof apiError.data?.detail === 'string'
        ? apiError.data.detail
        : t('onboarding:errors.submitFailed')
      toast.error(errorMessage)
    }
  }

  // Handle file upload
  const handleFileUpload = useCallback(async (fieldName: string, file: File, maxSize?: number) => {
    // Clear previous errors
    setUploadErrors((prev) => ({ ...prev, [fieldName]: '' }))

    // Validate file size
    if (maxSize && file.size > maxSize) {
      setUploadErrors((prev) => ({
        ...prev,
        [fieldName]: t('onboarding:validation.fileTooLarge', { maxSize: formatBytes(maxSize) }),
      }))
      return
    }

    try {
      const formData = new FormData()
      formData.append('file', file)

      const result = await uploadFile(formData).unwrap()

      // Store the uploaded file info
      setUploadedFiles((prev) => ({
        ...prev,
        [fieldName]: {
          mediaId: result.id,
          fileName: file.name,
          fileSize: file.size,
        },
      }))

      // Update form value with file ID
      form.setValue(fieldName, result.id, { shouldValidate: true })
    } catch (error) {
      const apiError = error as { data?: { detail?: string | Array<{ msg?: string }> } }
      let errorMessage = t('onboarding:validation.uploadFailed')

      if (apiError.data?.detail) {
        if (typeof apiError.data.detail === 'string') {
          errorMessage = apiError.data.detail
        } else if (Array.isArray(apiError.data.detail) && apiError.data.detail.length > 0) {
          // Extract message from Pydantic validation error format
          errorMessage = apiError.data.detail[0]?.msg || errorMessage
        }
      }

      setUploadErrors((prev) => ({
        ...prev,
        [fieldName]: errorMessage,
      }))
    }
  }, [uploadFile, form, t])

  // Remove uploaded file
  const handleRemoveFile = useCallback((fieldName: string) => {
    setUploadedFiles((prev) => {
      const newFiles = { ...prev }
      delete newFiles[fieldName]
      return newFiles
    })
    form.setValue(fieldName, '', { shouldValidate: true })
  }, [form])

  // Parse accept string to dropzone format
  const parseAccept = (accept?: string): Record<string, string[]> | undefined => {
    if (!accept) return undefined
    const result: Record<string, string[]> = {}
    accept.split(',').forEach((type) => {
      const trimmed = type.trim()
      if (trimmed.includes('/')) {
        result[trimmed] = []
      } else if (trimmed.startsWith('.')) {
        // Convert extension to mime type approximation
        result['application/octet-stream'] = [...(result['application/octet-stream'] || []), trimmed]
      }
    })
    return Object.keys(result).length > 0 ? result : undefined
  }

  // Get options for select fields
  const getSelectOptions = (options?: SelectOption[] | string[]): SelectOption[] => {
    if (!options) return []
    return options.map((opt) => {
      if (typeof opt === 'string') {
        return { value: opt, label: opt }
      }
      return opt
    })
  }

  // File upload field component
  const FileUploadField = ({ fieldName, config }: { fieldName: string; config: FieldConfig }) => {
    const uploadedFile = uploadedFiles[fieldName]
    const uploadError = uploadErrors[fieldName]
    const hasExistingFile = initialData?.[fieldName] && typeof initialData[fieldName] === 'string' && (initialData[fieldName] as string).length > 0

    const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
      onDrop: (acceptedFiles) => {
        if (acceptedFiles.length > 0) {
          handleFileUpload(fieldName, acceptedFiles[0], config.maxSize)
        }
      },
      accept: parseAccept(config.accept),
      maxSize: config.maxSize,
      maxFiles: 1,
      disabled: isUploading || isLoadingFiles,
    })

    // Show loading state when fetching existing file info
    if (isLoadingFiles && hasExistingFile && !uploadedFile) {
      return (
        <div className="flex items-center gap-3 p-3 border rounded-lg bg-muted/50">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="text-sm text-muted-foreground">{t('onboarding:fileUpload.loading')}</span>
        </div>
      )
    }

    // If file is uploaded, show the file info
    if (uploadedFile) {
      return (
        <div className="flex items-center gap-3 p-3 border rounded-lg bg-muted/50">
          <div className="flex-shrink-0">
            {uploadedFile.fileName.match(/\.(jpg|jpeg|png|gif|webp)$/i) ? (
              <Image className="h-8 w-8 text-muted-foreground" />
            ) : uploadedFile.fileName.match(/\.pdf$/i) ? (
              <FileText className="h-8 w-8 text-muted-foreground" />
            ) : (
              <FileIcon className="h-8 w-8 text-muted-foreground" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{uploadedFile.fileName}</p>
            <p className="text-xs text-muted-foreground">{formatBytes(uploadedFile.fileSize)}</p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 flex-shrink-0"
            onClick={() => handleRemoveFile(fieldName)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      )
    }

    return (
      <div className="space-y-2">
        <div
          {...getRootProps()}
          className={cn(
            'border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors',
            isDragActive && !isDragReject && 'border-primary bg-primary/5',
            isDragReject && 'border-destructive bg-destructive/5',
            isUploading && 'opacity-50 cursor-not-allowed',
            !isDragActive && !isUploading && 'hover:border-primary/50 hover:bg-muted/50'
          )}
        >
          <input {...getInputProps()} />
          <Upload className="mx-auto h-10 w-10 text-muted-foreground mb-3" />
          {isDragActive ? (
            isDragReject ? (
              <p className="text-destructive text-sm">{t('onboarding:fileUpload.dragReject')}</p>
            ) : (
              <p className="text-primary text-sm">{t('onboarding:fileUpload.dragActive')}</p>
            )
          ) : (
            <>
              <p className="text-sm text-muted-foreground mb-1">
                {t('onboarding:fileUpload.placeholder')}
              </p>
              {config.maxSize && (
                <p className="text-xs text-muted-foreground">
                  {t('onboarding:fileUpload.maxSize', { size: formatBytes(config.maxSize) })}
                </p>
              )}
            </>
          )}
        </div>
        {uploadError && <p className="text-sm text-destructive">{typeof uploadError === 'string' ? uploadError : t('onboarding:validation.uploadFailed')}</p>}
      </div>
    )
  }

  const renderField = (fieldName: string, fieldConfig: FieldConfig) => {
    const fieldType = fieldConfig.type || 'string'
    const label = fieldConfig.label || fieldName
    const description = fieldConfig.description
    const placeholder = fieldConfig.placeholder

    // Checkbox has a different layout
    if (fieldType === 'checkbox') {
      return (
        <FormField
          key={fieldName}
          control={form.control}
          name={fieldName}
          render={({ field }) => (
            <FormItem className="flex flex-row items-start space-x-3 space-y-0 rounded-md border p-4">
              <FormControl>
                <Checkbox
                  checked={field.value as boolean}
                  onCheckedChange={field.onChange}
                />
              </FormControl>
              <div className="space-y-1 leading-none">
                <FormLabel className="font-normal">
                  {label}
                  {fieldConfig.required === false && (
                    <span className="text-muted-foreground text-sm ml-1">
                      ({t('common:optional')})
                    </span>
                  )}
                </FormLabel>
                {description && <FormDescription>{description}</FormDescription>}
              </div>
            </FormItem>
          )}
        />
      )
    }

    return (
      <FormField
        key={fieldName}
        control={form.control}
        name={fieldName}
        render={({ field }) => (
          <FormItem>
            <FormLabel>
              {label}
              {fieldConfig.required === false && (
                <span className="text-muted-foreground text-sm ml-1">
                  ({t('common:optional')})
                </span>
              )}
            </FormLabel>
            <FormControl>
              {fieldType === 'textarea' ? (
                <Textarea
                  placeholder={placeholder}
                  rows={fieldConfig.rows || 4}
                  {...field}
                  value={field.value as string}
                />
              ) : fieldType === 'select' ? (
                <Select
                  value={field.value as string}
                  onValueChange={field.onChange}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder={placeholder} />
                  </SelectTrigger>
                  <SelectContent>
                    {getSelectOptions(fieldConfig.options).map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : fieldType === 'file' ? (
                <FileUploadField fieldName={fieldName} config={fieldConfig} />
              ) : fieldType === 'date' ? (
                <DatePicker
                  value={field.value as string}
                  onChange={field.onChange}
                  placeholder={placeholder}
                  minDate={fieldConfig.minDate ? parseDate(fieldConfig.minDate, 'yyyy-MM-dd', new Date()) : undefined}
                  maxDate={fieldConfig.maxDate ? parseDate(fieldConfig.maxDate, 'yyyy-MM-dd', new Date()) : undefined}
                  dateFormat={fieldConfig.dateFormat}
                />
              ) : fieldType === 'phone' ? (
                <Input
                  type="tel"
                  placeholder={placeholder || '+27 12 345 6789'}
                  {...field}
                  value={field.value as string}
                />
              ) : fieldType === 'radio' ? (
                <RadioGroup
                  value={field.value as string}
                  onValueChange={field.onChange}
                  className={cn(
                    fieldConfig.layout === 'horizontal' ? 'flex flex-wrap gap-4' : 'space-y-2'
                  )}
                >
                  {getSelectOptions(fieldConfig.options).map((option) => (
                    <div key={option.value} className="flex items-center gap-2">
                      <RadioGroupItem value={option.value} id={`${fieldName}-${option.value}`} />
                      <Label htmlFor={`${fieldName}-${option.value}`} className="font-normal cursor-pointer">
                        {option.label}
                      </Label>
                    </div>
                  ))}
                </RadioGroup>
              ) : fieldType === 'multiselect' ? (
                <MultiSelect
                  options={getSelectOptions(fieldConfig.options)}
                  value={field.value as string[]}
                  onChange={field.onChange}
                  placeholder={placeholder}
                  maxSelections={fieldConfig.maxSelections}
                />
              ) : (
                <Input
                  type={fieldType === 'number' ? 'number' : fieldType === 'email' ? 'email' : 'text'}
                  placeholder={placeholder}
                  {...field}
                  value={field.value as string | number}
                />
              )}
            </FormControl>
            {description && <FormDescription>{description}</FormDescription>}
            <FormMessage />
          </FormItem>
        )}
      />
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">{step.name}</h2>
        {step.description && (
          <p className="text-muted-foreground mt-2">{step.description}</p>
        )}
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          {Object.entries(step.required_fields).map(([fieldName, fieldConfig]) =>
            renderField(fieldName, fieldConfig as FieldConfig)
          )}

          <div className="flex gap-2">
            {onBack && (
              <Button type="button" variant="outline" onClick={onBack}>
                {t('common:buttons.back')}
              </Button>
            )}
            <Button type="submit" disabled={isLoading}>
              {isLoading
                ? t('common:common.saving')
                : isLastStep
                  ? t('common:buttons.submit')
                  : t('common:buttons.next')}
            </Button>
          </div>
        </form>
      </Form>
    </div>
  )
}
