import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { ArrowLeft, GripVertical, Plus, Pencil, Trash2, X } from 'lucide-react'
import { FieldBuilder, type FieldConfig } from '@/features/onboarding/field-builder'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import {
  useGetAdminUserTypeQuery,
  useGetAdminOnboardingStepsQuery,
  useCreateOnboardingStepMutation,
  useUpdateOnboardingStepMutation,
  useDeleteOnboardingStepMutation,
  type OnboardingStep,
  type CreateOnboardingStepRequest,
  type UpdateOnboardingStepRequest,
} from '@/store/api/onboardingApi'

interface StepFormData {
  name: string
  code: string
  description: string
  step_order: number
  required_fields: Record<string, FieldConfig>
  requires_verification: boolean
  is_active: boolean
}

const defaultStepFormData: StepFormData = {
  name: '',
  code: '',
  description: '',
  step_order: 1,
  required_fields: {},
  requires_verification: false,
  is_active: true,
}

interface StepFormProps {
  formData: StepFormData
  setFormData: React.Dispatch<React.SetStateAction<StepFormData>>
  onFieldsChange: (fields: Record<string, FieldConfig>) => void
  t: (key: string) => string
  editingStepId?: string | null
}

function StepForm({ formData, setFormData, onFieldsChange, t, editingStepId }: StepFormProps) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="step_name">{t('onboardingSteps.form.name')}</Label>
          <Input
            id="step_name"
            value={formData.name}
            onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
            placeholder={t('onboardingSteps.form.namePlaceholder')}
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="step_code">{t('onboardingSteps.form.code')}</Label>
          <Input
            id="step_code"
            value={formData.code}
            onChange={(e) => setFormData((prev) => ({ ...prev, code: e.target.value }))}
            placeholder={t('onboardingSteps.form.codePlaceholder')}
            required
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="step_description">{t('onboardingSteps.form.description')}</Label>
        <Textarea
          id="step_description"
          value={formData.description}
          onChange={(e) => setFormData((prev) => ({ ...prev, description: e.target.value }))}
          placeholder={t('onboardingSteps.form.descriptionPlaceholder')}
          rows={2}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="space-y-2">
          <Label htmlFor="step_order">{t('onboardingSteps.form.stepOrder')}</Label>
          <Input
            id="step_order"
            type="number"
            value={formData.step_order}
            onChange={(e) => setFormData((prev) => ({ ...prev, step_order: parseInt(e.target.value) || 1 }))}
            min={1}
          />
        </div>
        <div className="flex items-center justify-between md:col-span-2 p-3 border rounded-lg">
          <div>
            <Label>{t('onboardingSteps.form.isActive')}</Label>
            <p className="text-sm text-muted-foreground">
              {t('onboardingSteps.form.isActiveDescription')}
            </p>
          </div>
          <Switch
            checked={formData.is_active}
            onCheckedChange={(checked) => setFormData((prev) => ({ ...prev, is_active: checked }))}
          />
        </div>
      </div>

      <div className="flex items-center justify-between p-3 border rounded-lg">
        <div>
          <Label>{t('onboardingSteps.form.requiresVerification')}</Label>
          <p className="text-sm text-muted-foreground">
            {t('onboardingSteps.form.requiresVerificationDescription')}
          </p>
        </div>
        <Switch
          checked={formData.requires_verification}
          onCheckedChange={(checked) => setFormData((prev) => ({ ...prev, requires_verification: checked }))}
        />
      </div>

      <div className="space-y-2">
        <Label>{t('onboardingSteps.form.requiredFields')}</Label>
        <p className="text-sm text-muted-foreground">
          {t('onboardingSteps.form.requiredFieldsDescription')}
        </p>
        <div className="border rounded-lg p-4 bg-muted/30">
          <FieldBuilder
            key={editingStepId ?? 'new'}
            value={formData.required_fields}
            onChange={onFieldsChange}
          />
        </div>
      </div>
    </div>
  )
}

function StepListSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="p-3 border rounded-lg">
          <div className="flex items-center gap-3">
            <Skeleton className="h-5 w-5" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-48" />
            </div>
            <Skeleton className="h-5 w-16" />
          </div>
        </div>
      ))}
    </div>
  )
}

export function OnboardingStepsPage() {
  const { t } = useTranslation('admin')
  const { id: userTypeId } = useParams<{ id: string }>()
  const navigate = useNavigate()

  // Fetch user type info
  const { data: userTypeData, isLoading: isLoadingUserType } = useGetAdminUserTypeQuery(userTypeId!, {
    skip: !userTypeId,
  })
  const userType = userTypeData

  // Fetch steps
  const { data: stepsData, isLoading: isLoadingSteps } = useGetAdminOnboardingStepsQuery(userTypeId!, {
    skip: !userTypeId,
  })
  const steps = stepsData?.items || []

  // Mutations
  const [createStep, { isLoading: isCreating }] = useCreateOnboardingStepMutation()
  const [updateStep, { isLoading: isUpdating }] = useUpdateOnboardingStepMutation()
  const [deleteStep, { isLoading: isDeleting }] = useDeleteOnboardingStepMutation()

  // UI state
  const [editingStep, setEditingStep] = useState<OnboardingStep | null>(null)
  const [isCreatingNew, setIsCreatingNew] = useState(false)
  const [deletingStep, setDeletingStep] = useState<OnboardingStep | null>(null)
  const [formData, setFormData] = useState<StepFormData>(defaultStepFormData)

  const isEditing = editingStep !== null || isCreatingNew

  const resetForm = useCallback(() => {
    setFormData({
      ...defaultStepFormData,
      step_order: steps.length + 1,
    })
  }, [steps.length])

  const startCreating = () => {
    resetForm()
    setEditingStep(null)
    setIsCreatingNew(true)
  }

  const startEditing = (step: OnboardingStep) => {
    setFormData({
      name: step.name,
      code: step.code,
      description: step.description || '',
      step_order: step.step_order,
      required_fields: step.required_fields as Record<string, FieldConfig>,
      requires_verification: step.requires_verification,
      is_active: step.is_active,
    })
    setIsCreatingNew(false)
    setEditingStep(step)
  }

  const cancelEditing = () => {
    setEditingStep(null)
    setIsCreatingNew(false)
    resetForm()
  }

  const handleFieldsChange = useCallback((fields: Record<string, FieldConfig>) => {
    setFormData((prev) => ({ ...prev, required_fields: fields }))
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!userTypeId) return

    if (editingStep) {
      // Update existing step
      try {
        const request: UpdateOnboardingStepRequest = {
          name: formData.name,
          code: formData.code,
          description: formData.description || null,
          step_order: formData.step_order,
          required_fields: formData.required_fields,
          requires_verification: formData.requires_verification,
          is_active: formData.is_active,
        }
        await updateStep({ id: editingStep.id, data: request, userTypeId }).unwrap()
        toast.success(t('onboardingSteps.toast.updateSuccess'))
        setEditingStep(null)
        resetForm()
      } catch (error: unknown) {
        const apiError = error as { data?: { detail?: string } }
        toast.error(apiError.data?.detail || t('onboardingSteps.toast.updateError'))
      }
    } else {
      // Create new step
      try {
        const request: CreateOnboardingStepRequest = {
          user_type_id: userTypeId,
          name: formData.name,
          code: formData.code,
          description: formData.description || undefined,
          step_order: formData.step_order,
          required_fields: formData.required_fields,
          requires_verification: formData.requires_verification,
          is_active: formData.is_active,
        }
        await createStep(request).unwrap()
        toast.success(t('onboardingSteps.toast.createSuccess'))
        setIsCreatingNew(false)
        resetForm()
      } catch (error: unknown) {
        const apiError = error as { data?: { detail?: string } }
        toast.error(apiError.data?.detail || t('onboardingSteps.toast.createError'))
      }
    }
  }

  const handleDelete = async () => {
    if (!deletingStep || !userTypeId) return

    try {
      await deleteStep({ id: deletingStep.id, userTypeId }).unwrap()
      toast.success(t('onboardingSteps.toast.deleteSuccess'))
      setDeletingStep(null)
      // If we were editing the deleted step, cancel editing
      if (editingStep?.id === deletingStep.id) {
        cancelEditing()
      }
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('onboardingSteps.toast.deleteError'))
    }
  }

  const sortedSteps = [...steps].sort((a, b) => a.step_order - b.step_order)

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => navigate('/platform-admin/user-types')}
        >
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <PageHeader
          title={
            isLoadingUserType
              ? t('onboardingSteps.pageTitle')
              : t('onboardingSteps.pageTitleWithUserType', { userType: userType?.name })
          }
          description={t('onboardingSteps.pageDescription')}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Steps List Panel */}
        <Card className="lg:col-span-1">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg">{t('onboardingSteps.stepsListTitle')}</CardTitle>
              <Button onClick={startCreating} size="sm" disabled={isCreatingNew}>
                <Plus className="h-4 w-4 mr-1" />
                {t('onboardingSteps.addStep')}
              </Button>
            </div>
            <CardDescription>{t('onboardingSteps.stepsListDescription')}</CardDescription>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[calc(100vh-320px)]">
              {isLoadingSteps ? (
                <StepListSkeleton />
              ) : sortedSteps.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  {t('onboardingSteps.emptyMessage')}
                </div>
              ) : (
                <div className="space-y-2 pr-4">
                  {sortedSteps.map((step) => (
                    <div
                      key={step.id}
                      className={`flex items-center gap-3 p-3 border rounded-lg cursor-pointer transition-colors ${
                        editingStep?.id === step.id
                          ? 'bg-primary/10 border-primary'
                          : 'bg-card hover:bg-muted/50'
                      }`}
                      onClick={() => startEditing(step)}
                    >
                      <GripVertical className="h-5 w-5 text-muted-foreground flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium truncate">{step.name}</span>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <code className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                            {step.code}
                          </code>
                          <Badge variant="outline" className="text-xs">
                            #{step.step_order}
                          </Badge>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <Badge variant={step.is_active ? 'default' : 'secondary'} className="text-xs">
                          {step.is_active ? t('onboardingSteps.active') : t('onboardingSteps.inactive')}
                        </Badge>
                        {step.requires_verification && (
                          <Badge variant="outline" className="text-xs">
                            {t('onboardingSteps.verification')}
                          </Badge>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Editor Panel */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg">
                  {isCreatingNew
                    ? t('onboardingSteps.createStep.title')
                    : editingStep
                      ? t('onboardingSteps.editStep.title')
                      : t('onboardingSteps.editorTitle')}
                </CardTitle>
                <CardDescription>
                  {isCreatingNew
                    ? t('onboardingSteps.createStep.description')
                    : editingStep
                      ? t('onboardingSteps.editStep.description')
                      : t('onboardingSteps.editorDescription')}
                </CardDescription>
              </div>
              {isEditing && (
                <div className="flex items-center gap-2">
                  {editingStep && (
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setDeletingStep(editingStep)}
                      className="text-destructive hover:text-destructive"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                  <Button variant="ghost" size="icon" onClick={cancelEditing}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {isEditing ? (
              <form onSubmit={handleSubmit}>
                <ScrollArea className="h-[calc(100vh-380px)] pr-4">
                  <StepForm
                    formData={formData}
                    setFormData={setFormData}
                    onFieldsChange={handleFieldsChange}
                    t={t}
                    editingStepId={editingStep?.id}
                  />
                </ScrollArea>
                <div className="flex justify-end gap-2 pt-4 border-t mt-4">
                  <Button type="button" variant="outline" onClick={cancelEditing}>
                    {t('common.cancel')}
                  </Button>
                  <Button type="submit" disabled={isCreating || isUpdating}>
                    {editingStep
                      ? isUpdating
                        ? t('common.saving')
                        : t('common.save')
                      : isCreating
                        ? t('common.creating')
                        : t('common.create')}
                  </Button>
                </div>
              </form>
            ) : (
              <div className="h-[calc(100vh-380px)] flex flex-col items-center justify-center text-center text-muted-foreground">
                <Pencil className="h-12 w-12 mb-4 opacity-50" />
                <p className="text-lg font-medium">{t('onboardingSteps.selectStepPrompt')}</p>
                <p className="text-sm mt-1">{t('onboardingSteps.selectStepDescription')}</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deletingStep}
        onOpenChange={() => setDeletingStep(null)}
        title={t('onboardingSteps.deleteDialog.title')}
        description={t('onboardingSteps.deleteDialog.description', { name: deletingStep?.name })}
        confirmLabel={t('onboardingSteps.deleteDialog.confirm')}
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />
    </div>
  )
}
