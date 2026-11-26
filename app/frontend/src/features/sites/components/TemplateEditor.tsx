import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { RotateCcw } from 'lucide-react'
import { toast } from '@/lib/toast'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useResetSiteTemplateMutation, useUpdateSiteTemplateMutation } from '../sitesApi'
import { getServerError } from '../errors'
import {
  MAX_BODY_LENGTH,
  MAX_TITLE_LENGTH,
  findUnknownPlaceholders,
  insertPlaceholder,
  isTemplateChanged,
  renderPreview,
  sampleValues,
} from '../templatePreview'
import type { Site, SiteTemplate } from '@/types/site'

interface TemplateEditorProps {
  site: Site
  template: SiteTemplate
  canWrite: boolean
}

type FieldName = 'title' | 'body'

/** Editor for one advisory type: title, body, placeholders, live preview, reset. */
export function TemplateEditor({ site, template, canWrite }: TemplateEditorProps) {
  const { t } = useTranslation(['sites', 'backend'])
  const [title, setTitle] = useState(template.title)
  const [body, setBody] = useState(template.body)
  const [serverError, setServerError] = useState<{ message: string; detail: string | null } | null>(
    null
  )
  const [resetOpen, setResetOpen] = useState(false)
  const [active, setActive] = useState<FieldName>('body')
  const titleRef = useRef<HTMLInputElement>(null)
  const bodyRef = useRef<HTMLTextAreaElement>(null)
  const [saveTemplate, { isLoading: isSaving }] = useUpdateSiteTemplateMutation()
  const [resetTemplate, { isLoading: isResetting }] = useResetSiteTemplateMutation()

  // Follow the server copy after a save, reset or refetch.
  useEffect(() => {
    setTitle(template.title)
    setBody(template.body)
  }, [template.title, template.body])

  const allowed = template.allowed_placeholders
  const unknown = useMemo(
    () => [...new Set([...findUnknownPlaceholders(title, allowed), ...findUnknownPlaceholders(body, allowed)])],
    [title, body, allowed]
  )
  const samples = useMemo(() => sampleValues(site.name), [site.name])
  const changed = isTemplateChanged({ title, body }, template)
  const isDefault = template.title === template.default_title && template.body === template.default_body
  const invalid =
    unknown.length > 0 ||
    title.trim() === '' ||
    body.trim() === '' ||
    title.length > MAX_TITLE_LENGTH ||
    body.length > MAX_BODY_LENGTH

  const insert = (name: string) => {
    const el = active === 'title' ? titleRef.current : bodyRef.current
    const text = active === 'title' ? title : body
    const start = el?.selectionStart ?? text.length
    const end = el?.selectionEnd ?? text.length
    const result = insertPlaceholder(text, start, end, name)
    if (active === 'title') setTitle(result.text)
    else setBody(result.text)
    requestAnimationFrame(() => {
      el?.focus()
      el?.setSelectionRange(result.cursor, result.cursor)
    })
  }

  const save = async () => {
    setServerError(null)
    try {
      await saveTemplate({
        siteId: site.id,
        advisoryType: template.advisory_type,
        title,
        body,
      }).unwrap()
      toast.success(t('sites:templates.saved'))
    } catch (error) {
      setServerError(getServerError(error, t))
    }
  }

  const reset = async () => {
    setServerError(null)
    try {
      await resetTemplate({ siteId: site.id, advisoryType: template.advisory_type }).unwrap()
      toast.success(t('sites:templates.resetDone'))
    } catch (error) {
      setServerError(getServerError(error, t))
    } finally {
      setResetOpen(false)
    }
  }

  const type = template.advisory_type

  return (
    <Card data-testid={`template-${type}`}>
      <CardHeader>
        <CardTitle>{t(`sites:templates.types.${type}.title`)}</CardTitle>
        <CardDescription>{t(`sites:templates.types.${type}.description`)}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {serverError && (
          <Alert variant="destructive" role="alert">
            <AlertTitle>{serverError.message}</AlertTitle>
            {serverError.detail && <AlertDescription>{serverError.detail}</AlertDescription>}
          </Alert>
        )}

        <div className="space-y-2">
          <Label htmlFor={`tpl-title-${type}`}>{t('sites:templates.titleLabel')}</Label>
          <Input
            id={`tpl-title-${type}`}
            ref={titleRef}
            value={title}
            disabled={!canWrite}
            onFocus={() => setActive('title')}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor={`tpl-body-${type}`}>{t('sites:templates.bodyLabel')}</Label>
          <Textarea
            id={`tpl-body-${type}`}
            ref={bodyRef}
            rows={4}
            value={body}
            disabled={!canWrite}
            onFocus={() => setActive('body')}
            onChange={(e) => setBody(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            {t('sites:templates.counter', {
              title: title.length,
              maxTitle: MAX_TITLE_LENGTH,
              body: body.length,
              maxBody: MAX_BODY_LENGTH,
            })}
          </p>
        </div>

        <div className="space-y-2">
          <Label>{t('sites:templates.placeholders')}</Label>
          <div className="flex flex-wrap gap-2">
            {allowed.map((name) => (
              <Button
                key={name}
                type="button"
                variant="outline"
                size="sm"
                disabled={!canWrite}
                title={t(`sites:templates.placeholderHelp.${name}`, { defaultValue: name })}
                onClick={() => insert(name)}
              >
                <code>{`{${name}}`}</code>
              </Button>
            ))}
          </div>
          {canWrite && (
            <p className="text-xs text-muted-foreground">{t('sites:templates.insertHint')}</p>
          )}
        </div>

        {unknown.length > 0 && (
          <Alert variant="destructive" role="alert">
            <AlertTitle>{t('sites:templates.unknownTitle')}</AlertTitle>
            <AlertDescription>
              {t('sites:templates.unknown', {
                names: unknown.map((n) => `{${n}}`).join(', '),
              })}
            </AlertDescription>
          </Alert>
        )}

        <div className="space-y-1 rounded-md border bg-muted/40 p-3" aria-live="polite">
          <p className="text-xs font-medium uppercase text-muted-foreground">
            {t('sites:templates.preview')}
          </p>
          <p className="font-semibold" data-testid={`preview-title-${type}`}>
            {renderPreview(title, samples, allowed)}
          </p>
          <p className="text-sm" data-testid={`preview-body-${type}`}>
            {renderPreview(body, samples, allowed)}
          </p>
          <p className="pt-1 text-xs text-muted-foreground">{t('sites:templates.previewNote')}</p>
        </div>

        {canWrite && (
          <div className="flex gap-2">
            <Button onClick={save} disabled={!changed || invalid || isSaving}>
              {isSaving ? t('sites:actions.saving') : t('sites:actions.save')}
            </Button>
            <Button
              variant="outline"
              disabled={isDefault || isResetting}
              onClick={() => setResetOpen(true)}
            >
              <RotateCcw className="mr-2 h-4 w-4" />
              {t('sites:templates.reset')}
            </Button>
          </div>
        )}
      </CardContent>

      <ConfirmDialog
        open={resetOpen}
        onOpenChange={setResetOpen}
        title={t('sites:templates.resetConfirm.title')}
        description={t('sites:templates.resetConfirm.description')}
        confirmLabel={t('sites:templates.resetConfirm.confirm')}
        onConfirm={reset}
        isLoading={isResetting}
      />
    </Card>
  )
}
