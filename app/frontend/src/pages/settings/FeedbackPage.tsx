import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { format } from 'date-fns'
import { MessageSquare, ChevronDown, ChevronUp, Bell, Send } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  useGetMyFeedbackQuery,
  useCreateFeedbackReplyMutation,
  useMarkFeedbackViewedMutation,
} from '@/features/feedback/feedbackApi'
import type { Feedback, FeedbackStatus, FeedbackType } from '@/features/feedback/types'

export function FeedbackPage() {
  const { t } = useTranslation(['feedback', 'settings'])
  const { data, isLoading } = useGetMyFeedbackQuery({ limit: 100, offset: 0 })
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  const toggleExpanded = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const getStatusBadgeVariant = (status: FeedbackStatus) => {
    switch (status) {
      case 'new':
        return 'default'
      case 'in_review':
        return 'secondary'
      case 'resolved':
        return 'outline'
      case 'dismissed':
        return 'destructive'
      default:
        return 'default'
    }
  }

  const getTypeBadgeVariant = (type: FeedbackType) => {
    switch (type) {
      case 'bug':
        return 'destructive'
      case 'suggestion':
        return 'default'
      case 'complaint':
        return 'secondary'
      case 'praise':
        return 'outline'
      case 'other':
        return 'outline'
      default:
        return 'default'
    }
  }

  const feedbacks = data?.items || []

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">{t('feedback:user.title')}</h2>
        <p className="text-muted-foreground">{t('feedback:user.description')}</p>
      </div>

      {isLoading ? (
        <Card>
          <CardContent className="py-8">
            <p className="text-center text-muted-foreground">{t('feedback:admin.detail.loading')}</p>
          </CardContent>
        </Card>
      ) : feedbacks.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <MessageSquare className="mx-auto h-12 w-12 text-muted-foreground/50" />
            <h3 className="mt-4 text-lg font-semibold">{t('feedback:user.noFeedback')}</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              {t('feedback:widget.openButton')}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {feedbacks.map((feedback) => (
            <FeedbackItem
              key={feedback.id}
              feedback={feedback}
              isExpanded={expandedIds.has(feedback.id)}
              onToggle={() => toggleExpanded(feedback.id)}
              getStatusBadgeVariant={getStatusBadgeVariant}
              getTypeBadgeVariant={getTypeBadgeVariant}
              t={t}
            />
          ))}
        </div>
      )}
    </div>
  )
}

interface FeedbackItemProps {
  feedback: Feedback
  isExpanded: boolean
  onToggle: () => void
  getStatusBadgeVariant: (status: FeedbackStatus) => 'default' | 'secondary' | 'outline' | 'destructive'
  getTypeBadgeVariant: (type: FeedbackType) => 'default' | 'secondary' | 'outline' | 'destructive'
  t: (key: string) => string
}

function FeedbackItem({
  feedback,
  isExpanded,
  onToggle,
  getStatusBadgeVariant,
  getTypeBadgeVariant,
  t,
}: FeedbackItemProps) {
  const [replyMessage, setReplyMessage] = useState('')
  const [createReply, { isLoading: isSubmittingReply }] = useCreateFeedbackReplyMutation()
  const [markViewed] = useMarkFeedbackViewedMutation()

  const hasReplies = feedback.replies && feedback.replies.length > 0
  const hasUnread = feedback.has_unread_replies

  // Mark as viewed when expanded and has unread replies
  useEffect(() => {
    if (isExpanded && hasUnread) {
      markViewed(feedback.id)
    }
  }, [isExpanded, hasUnread, feedback.id, markViewed])

  const handleSubmitReply = async () => {
    if (!replyMessage.trim()) return

    try {
      await createReply({
        feedbackId: feedback.id,
        data: { message: replyMessage.trim() },
      }).unwrap()
      setReplyMessage('')
    } catch {
      // Error handled by RTK Query
    }
  }

  return (
    <Collapsible open={isExpanded} onOpenChange={onToggle}>
      <Card className={hasUnread ? 'ring-2 ring-primary' : ''}>
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <CardTitle className="text-base">{feedback.subject}</CardTitle>
                {hasUnread && (
                  <Badge variant="default" className="text-xs">
                    <Bell className="h-3 w-3 mr-1" />
                    {t('feedback:user.newReply')}
                  </Badge>
                )}
              </div>
              <CardDescription>
                {feedback.created_time
                  ? format(new Date(feedback.created_time), 'PPp')
                  : '—'}
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={getTypeBadgeVariant(feedback.type)}>
                {t(`feedback:form.fields.type.options.${feedback.type}`)}
              </Badge>
              <Badge variant={getStatusBadgeVariant(feedback.status)}>
                {t(`feedback:admin.status.${feedback.status}`)}
              </Badge>
              <CollapsibleTrigger asChild>
                <Button variant="ghost" size="sm">
                  {isExpanded ? (
                    <ChevronUp className="h-4 w-4" />
                  ) : (
                    <ChevronDown className="h-4 w-4" />
                  )}
                </Button>
              </CollapsibleTrigger>
            </div>
          </div>
        </CardHeader>
        <CollapsibleContent>
          <CardContent className="pt-0 space-y-4">
            <Separator />

            {/* Original message */}
            <div className="bg-muted/30 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-medium text-muted-foreground">
                  {t('feedback:user.yourMessage')}
                </span>
                <span className="text-xs text-muted-foreground">
                  {feedback.created_time ? format(new Date(feedback.created_time), 'PPp') : ''}
                </span>
              </div>
              <p className="text-sm whitespace-pre-wrap">{feedback.message}</p>
            </div>

            {feedback.rating && (
              <div>
                <h4 className="text-sm font-medium mb-1">{t('feedback:form.fields.rating.label')}</h4>
                <div className="flex items-center gap-1">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <span
                      key={i}
                      className={i < feedback.rating! ? 'text-yellow-500' : 'text-gray-300'}
                    >
                      ★
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Conversation thread */}
            {hasReplies && (
              <div className="space-y-3">
                <h4 className="text-sm font-medium">{t('feedback:user.conversation')}</h4>
                {feedback.replies.map((reply) => (
                  <div
                    key={reply.id}
                    className={`rounded-lg p-3 ${
                      reply.is_admin_reply
                        ? 'bg-primary/10 ml-4'
                        : 'bg-muted/30 mr-4'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-medium">
                        {reply.is_admin_reply
                          ? t('feedback:user.adminReply')
                          : t('feedback:user.you')}
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

            {/* Legacy admin_response display (for backward compatibility) */}
            {feedback.admin_response && !hasReplies && (
              <div className="bg-primary/10 rounded-lg p-3 ml-4">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-medium">
                    {t('feedback:user.adminReply')}
                  </span>
                  {feedback.responded_at && (
                    <span className="text-xs text-muted-foreground">
                      {format(new Date(feedback.responded_at), 'PPp')}
                    </span>
                  )}
                </div>
                <p className="text-sm whitespace-pre-wrap">{feedback.admin_response}</p>
              </div>
            )}

            {/* No response yet message */}
            {!hasReplies && !feedback.admin_response && feedback.status === 'new' && (
              <p className="text-sm text-muted-foreground italic">
                {t('feedback:user.noResponse')}
              </p>
            )}

            {/* Reply form - only show if feedback is not resolved/dismissed */}
            {feedback.status !== 'resolved' && feedback.status !== 'dismissed' && (
              <>
                <Separator />
                <div className="space-y-2">
                  <h4 className="text-sm font-medium">{t('feedback:user.replyTitle')}</h4>
                  <Textarea
                    value={replyMessage}
                    onChange={(e) => setReplyMessage(e.target.value)}
                    placeholder={t('feedback:user.replyPlaceholder')}
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
                        ? t('feedback:user.sending')
                        : t('feedback:user.sendReply')}
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}
