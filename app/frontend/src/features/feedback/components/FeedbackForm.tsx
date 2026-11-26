import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { Camera, Upload, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
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
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  FormDescription,
} from '@/components/ui/form'
import { StarRating } from './StarRating'
import { useSubmitFeedbackMutation, useUploadAttachmentMutation } from '../feedbackApi'
import { useUploadFileMutation } from '@/features/files/filesApi'
import { MediaUse } from '@/types/generated'

const createFeedbackSchema = (t: (key: string) => string) =>
  z.object({
    type: z.enum(['bug', 'suggestion', 'complaint', 'praise', 'other'] as const, {
      message: t('feedback:form.validation.typeRequired'),
    }),
    rating: z.number().min(1).max(5).optional().nullable(),
    subject: z
      .string()
      .min(1, t('feedback:form.validation.subjectRequired'))
      .max(100, t('feedback:form.validation.subjectTooLong')),
    message: z
      .string()
      .min(1, t('feedback:form.validation.messageRequired'))
      .max(2000, t('feedback:form.validation.messageTooLong')),
  })

type FeedbackFormData = z.infer<ReturnType<typeof createFeedbackSchema>>

interface FeedbackFormProps {
  onSuccess?: () => void
  /** Pre-populate fields (e.g. when reporting an error from the error page). */
  defaultValues?: Partial<Pick<FeedbackFormData, 'type' | 'subject' | 'message' | 'rating'>>
  /**
   * Optional structured payload uploaded as a JSON attachment alongside the
   * feedback (e.g. error diagnostics). Failures are non-blocking.
   */
  diagnostics?: unknown
  /**
   * Filename for the diagnostics attachment. Uses a `.txt` extension because
   * the per-organization default allowed-extensions list does not include
   * `json`; the content is still pretty-printed JSON, readable as text.
   */
  diagnosticsFilename?: string
}

export function FeedbackForm({
  onSuccess,
  defaultValues,
  diagnostics,
  diagnosticsFilename = 'error-diagnostics.txt',
}: FeedbackFormProps) {
  const { t } = useTranslation(['feedback'])
  const [submitFeedback, { isLoading: isSubmitting }] = useSubmitFeedbackMutation()
  const [uploadAttachment] = useUploadAttachmentMutation()
  const [uploadFile] = useUploadFileMutation()
  const [screenshot, setScreenshot] = useState<File | null>(null)
  const [attachment, setAttachment] = useState<File | null>(null)
  const [isUploading, setIsUploading] = useState(false)

  const isLoading = isSubmitting || isUploading

  const form = useForm<FeedbackFormData>({
    resolver: zodResolver(createFeedbackSchema(t)),
    defaultValues: {
      type: defaultValues?.type,
      rating: defaultValues?.rating ?? null,
      subject: defaultValues?.subject ?? '',
      message: defaultValues?.message ?? '',
    },
  })

  // When the form is opened pre-populated (e.g. an error report), validate up
  // front so the submit button is enabled without the user editing a field.
  useEffect(() => {
    if (defaultValues) {
      void form.trigger()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const captureScreenshot = async () => {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
        toast.error(t('feedback:form.screenshot.notSupported'))
        return
      }

      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
      })

      const video = document.createElement('video')
      video.srcObject = stream
      video.play()

      await new Promise((resolve) => {
        video.onloadedmetadata = resolve
      })

      const canvas = document.createElement('canvas')
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      const ctx = canvas.getContext('2d')
      ctx?.drawImage(video, 0, 0)

      stream.getTracks().forEach((track) => track.stop())

      canvas.toBlob((blob) => {
        if (blob) {
          const file = new File([blob], 'screenshot.png', { type: 'image/png' })
          setScreenshot(file)
          toast.success(t('feedback:form.screenshot.captured'))
        }
      })
    } catch (error) {
      if ((error as Error).name !== 'NotAllowedError') {
        toast.error(t('feedback:form.screenshot.error'))
      }
    }
  }

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    const maxSize = 5 * 1024 * 1024 // 5MB
    if (file.size > maxSize) {
      toast.error(t('feedback:form.attachment.tooLarge'))
      return
    }

    const allowedTypes = ['image/png', 'image/jpeg', 'image/jpg', 'application/pdf']
    if (!allowedTypes.includes(file.type)) {
      toast.error(t('feedback:form.attachment.invalidType'))
      return
    }

    setAttachment(file)
  }

  const uploadFileToStorage = async (file: File, feedbackId: string): Promise<void> => {
    // Upload the file via the files API
    const formData = new FormData()
    formData.append('file', file)
    formData.append('media_use', MediaUse.OTHER)

    const fileResult = await uploadFile(formData).unwrap()

    // Then record the attachment metadata with the file ID
    await uploadAttachment({
      feedbackId,
      data: {
        file_path: fileResult.id, // Store file ID for retrieval
        file_type: file.type,
        file_size_bytes: file.size,
      },
    }).unwrap()
  }

  const onSubmit = async (data: FeedbackFormData) => {
    try {
      const response = await submitFeedback({
        type: data.type,
        rating: data.rating,
        subject: data.subject,
        message: data.message,
        page_url: window.location.href,
        user_agent: navigator.userAgent,
        screen_resolution: `${window.screen.width}x${window.screen.height}`,
      }).unwrap()

      // Upload files if they exist
      setIsUploading(true)
      try {
        // Upload screenshot if exists
        if (screenshot) {
          await uploadFileToStorage(screenshot, response.feedback.id)
        }

        // Upload attachment if exists
        if (attachment) {
          await uploadFileToStorage(attachment, response.feedback.id)
        }

        // Upload diagnostics payload (e.g. error report context) if provided
        if (diagnostics !== undefined) {
          const diagnosticsFile = new File(
            [JSON.stringify(diagnostics, null, 2)],
            diagnosticsFilename,
            { type: 'text/plain' },
          )
          await uploadFileToStorage(diagnosticsFile, response.feedback.id)
        }
      } catch {
        // Attachment upload failed - feedback was still submitted successfully
      } finally {
        setIsUploading(false)
      }

      toast.success(t('feedback:form.success'))
      form.reset()
      setScreenshot(null)
      setAttachment(null)
      onSuccess?.()
    } catch (error) {
      setIsUploading(false)
      const errorMessage =
        (error as { data?: { detail?: string }; message?: string })?.data?.detail ||
        (error as { message?: string })?.message ||
        t('feedback:form.error')
      toast.error(errorMessage)
    }
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <FormField
          control={form.control}
          name="type"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('feedback:form.fields.type.label')}</FormLabel>
              <Select
                onValueChange={field.onChange}
                value={field.value}
                disabled={isLoading}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder={t('feedback:form.fields.type.placeholder')} />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value="bug">{t('feedback:form.fields.type.options.bug')}</SelectItem>
                  <SelectItem value="suggestion">
                    {t('feedback:form.fields.type.options.suggestion')}
                  </SelectItem>
                  <SelectItem value="complaint">
                    {t('feedback:form.fields.type.options.complaint')}
                  </SelectItem>
                  <SelectItem value="praise">
                    {t('feedback:form.fields.type.options.praise')}
                  </SelectItem>
                  <SelectItem value="other">
                    {t('feedback:form.fields.type.options.other')}
                  </SelectItem>
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="rating"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('feedback:form.fields.rating.label')}</FormLabel>
              <FormControl>
                <StarRating
                  value={field.value || 0}
                  onChange={field.onChange}
                  disabled={isLoading}
                />
              </FormControl>
              <FormDescription>{t('feedback:form.fields.rating.description')}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="subject"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('feedback:form.fields.subject.label')}</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  placeholder={t('feedback:form.fields.subject.placeholder')}
                  disabled={isLoading}
                  maxLength={100}
                />
              </FormControl>
              <FormDescription>
                {field.value.length}/100 {t('feedback:form.fields.subject.characterCount')}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="message"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('feedback:form.fields.message.label')}</FormLabel>
              <FormControl>
                <Textarea
                  {...field}
                  placeholder={t('feedback:form.fields.message.placeholder')}
                  disabled={isLoading}
                  maxLength={2000}
                  rows={6}
                />
              </FormControl>
              <FormDescription>
                {field.value.length}/2000 {t('feedback:form.fields.message.characterCount')}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="space-y-2">
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={captureScreenshot}
              disabled={isLoading}
            >
              <Camera className="mr-2 h-4 w-4" />
              {t('feedback:form.screenshot.button')}
            </Button>
            <Button type="button" variant="outline" size="sm" disabled={isLoading} asChild>
              <label>
                <Upload className="mr-2 h-4 w-4" />
                {t('feedback:form.attachment.button')}
                <input
                  type="file"
                  className="hidden"
                  accept="image/png,image/jpeg,image/jpg,application/pdf"
                  onChange={handleFileUpload}
                  disabled={isLoading}
                />
              </label>
            </Button>
          </div>

          {screenshot && (
            <div className="relative inline-block">
              <img
                src={URL.createObjectURL(screenshot)}
                alt="Screenshot preview"
                className="h-20 w-auto rounded border"
              />
              <Button
                type="button"
                variant="destructive"
                size="icon"
                className="absolute -right-2 -top-2 h-6 w-6 rounded-full"
                onClick={() => setScreenshot(null)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          )}

          {attachment && (
            <div className="flex items-center gap-2 rounded border p-2">
              <span className="text-sm">{attachment.name}</span>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={() => setAttachment(null)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2">
          <Button type="submit" disabled={isLoading || !form.formState.isValid}>
            {isLoading ? t('feedback:form.submitting') : t('feedback:form.submit')}
          </Button>
        </div>
      </form>
    </Form>
  )
}
