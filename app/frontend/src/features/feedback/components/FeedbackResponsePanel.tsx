import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from '@/lib/toast'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { useUpdateFeedbackMutation, useCreateFeedbackReplyMutation } from '../feedbackApi'
import type { Feedback } from '../types'
import { format } from 'date-fns'
import { Send, User, Shield } from 'lucide-react'

interface FeedbackResponsePanelProps {
  feedback: Feedback
}

const responseSchema = z.object({
  status: z.enum(['new', 'in_review', 'resolved', 'dismissed']),
  admin_response: z.string().max(2000).optional(),
  admin_notes: z.string().max(2000).optional(),
})

type ResponseFormData = z.infer<typeof responseSchema>

export function FeedbackResponsePanel({ feedback }: FeedbackResponsePanelProps) {
  const { t } = useTranslation('feedback')
  const [isEditing, setIsEditing] = useState(false)
  const [replyMessage, setReplyMessage] = useState('')
  const [updateFeedback, { isLoading }] = useUpdateFeedbackMutation()
  const [createReply, { isLoading: isSubmittingReply }] = useCreateFeedbackReplyMutation()

  const form = useForm<ResponseFormData>({
    resolver: zodResolver(responseSchema),
    defaultValues: {
      status: feedback.status,
      admin_response: feedback.admin_response || '',
      admin_notes: feedback.admin_notes || '',
    },
  })

  const handleSubmit = async (data: ResponseFormData) => {
    try {
      await updateFeedback({
        id: feedback.id,
        data: {
          status: data.status,
          admin_response: data.admin_response || null,
          admin_notes: data.admin_notes || null,
        },
      }).unwrap()
      toast.success(t('admin.response.updateSuccess'))
      setIsEditing(false)
    } catch {
      toast.error(t('admin.response.updateError'))
    }
  }

  const handleCancel = () => {
    form.reset({
      status: feedback.status,
      admin_response: feedback.admin_response || '',
      admin_notes: feedback.admin_notes || '',
    })
    setIsEditing(false)
  }

  const handleSubmitReply = async () => {
    if (!replyMessage.trim()) return

    try {
      await createReply({
        feedbackId: feedback.id,
        data: { message: replyMessage.trim() },
      }).unwrap()
      setReplyMessage('')
      toast.success(t('admin.response.replySent'))
    } catch {
      toast.error(t('admin.response.replyError'))
    }
  }

  const hasReplies = feedback.replies && feedback.replies.length > 0

  return (
    <div className="space-y-4">
      {/* Conversation Thread Card */}
      <Card>
        <CardHeader>
          <CardTitle>{t('admin.response.conversation')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Original user message */}
          <div className="bg-muted/30 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              <User className="h-3 w-3 text-muted-foreground" />
              <span className="text-xs font-medium">
                {feedback.user_email || t('admin.response.user')}
              </span>
              <span className="text-xs text-muted-foreground">
                {feedback.created_time ? format(new Date(feedback.created_time), 'PPp') : ''}
              </span>
            </div>
            <p className="text-sm whitespace-pre-wrap">{feedback.message}</p>
          </div>

          {/* Legacy admin_response (for backward compatibility) */}
          {feedback.admin_response && !hasReplies && (
            <div className="bg-primary/10 rounded-lg p-3 ml-4">
              <div className="flex items-center gap-2 mb-1">
                <Shield className="h-3 w-3 text-primary" />
                <span className="text-xs font-medium">{t('admin.response.adminLabel')}</span>
                {feedback.responded_at && (
                  <span className="text-xs text-muted-foreground">
                    {format(new Date(feedback.responded_at), 'PPp')}
                  </span>
                )}
              </div>
              <p className="text-sm whitespace-pre-wrap">{feedback.admin_response}</p>
            </div>
          )}

          {/* Replies thread */}
          {hasReplies && (
            <div className="space-y-3">
              {feedback.replies.map((reply) => (
                <div
                  key={reply.id}
                  className={`rounded-lg p-3 ${
                    reply.is_admin_reply
                      ? 'bg-primary/10 ml-4'
                      : 'bg-muted/30'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    {reply.is_admin_reply ? (
                      <Shield className="h-3 w-3 text-primary" />
                    ) : (
                      <User className="h-3 w-3 text-muted-foreground" />
                    )}
                    <span className="text-xs font-medium">
                      {reply.is_admin_reply
                        ? t('admin.response.adminLabel')
                        : reply.user_email || t('admin.response.user')}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {reply.created_time
                        ? format(new Date(reply.created_time), 'PPp')
                        : ''}
                    </span>
                  </div>
                  <p className="text-sm whitespace-pre-wrap">{reply.message}</p>
                </div>
              ))}
            </div>
          )}

          {/* Reply form */}
          {feedback.status !== 'resolved' && feedback.status !== 'dismissed' && (
            <>
              <Separator />
              <div className="space-y-2">
                <Textarea
                  value={replyMessage}
                  onChange={(e) => setReplyMessage(e.target.value)}
                  placeholder={t('admin.response.replyPlaceholder')}
                  rows={3}
                  maxLength={5000}
                  disabled={isSubmittingReply}
                />
                <div className="flex justify-end">
                  <Button
                    size="sm"
                    onClick={handleSubmitReply}
                    disabled={!replyMessage.trim() || isSubmittingReply}
                  >
                    <Send className="h-4 w-4 mr-2" />
                    {isSubmittingReply
                      ? t('admin.response.sending')
                      : t('admin.response.sendReply')}
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Status & Notes Card */}
      <Card>
        <CardHeader>
          <CardTitle>{t('admin.response.statusAndNotes')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {!isEditing ? (
            <>
              <div>
                <h4 className="text-sm font-medium mb-2">{t('admin.response.status')}</h4>
                <Badge variant="default">{t(`admin.status.${feedback.status}`)}</Badge>
              </div>

              {feedback.admin_notes && (
                <>
                  <Separator />
                  <div>
                    <h4 className="text-sm font-medium mb-2">{t('admin.response.internalNotes')}</h4>
                    <p className="text-sm whitespace-pre-wrap text-muted-foreground">
                      {feedback.admin_notes}
                    </p>
                  </div>
                </>
              )}

              <Separator />
              <Button onClick={() => setIsEditing(true)} variant="outline" className="w-full">
                {t('admin.response.editStatusNotes')}
              </Button>
            </>
          ) : (
            <Form {...form}>
              <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
                <FormField
                  control={form.control}
                  name="status"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('admin.response.status')}</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="new">{t('admin.status.new')}</SelectItem>
                          <SelectItem value="in_review">{t('admin.status.in_review')}</SelectItem>
                          <SelectItem value="resolved">{t('admin.status.resolved')}</SelectItem>
                          <SelectItem value="dismissed">{t('admin.status.dismissed')}</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="admin_notes"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('admin.response.internalNotes')}</FormLabel>
                      <FormControl>
                        <Textarea
                          {...field}
                          placeholder={t('admin.response.internalNotesPlaceholder')}
                          rows={4}
                        />
                      </FormControl>
                      <p className="text-xs text-muted-foreground">
                        {t('admin.response.internalNotesHelp')}
                      </p>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="flex gap-2">
                  <Button type="submit" disabled={isLoading} className="flex-1">
                    {isLoading ? t('admin.response.saving') : t('admin.response.save')}
                  </Button>
                  <Button type="button" variant="outline" onClick={handleCancel} disabled={isLoading}>
                    {t('admin.response.cancel')}
                  </Button>
                </div>
              </form>
            </Form>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
