import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import type { Permission } from '@/features/permissions/types'

/**
 * Zod schema for permission form validation
 * Code must match pattern: resource:action (lowercase with underscores allowed)
 */
const createPermissionSchema = (t: (key: string) => string) =>
  z.object({
    code: z
      .string()
      .min(1, t('permissions.validation.codeRequired'))
      .regex(
        /^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$/,
        t('permissions.validation.codeFormat')
      ),
    name: z
      .string()
      .min(1, t('permissions.validation.nameRequired'))
      .max(100, t('permissions.validation.nameTooLong')),
    description: z
      .string()
      .max(500, t('permissions.validation.descriptionTooLong'))
      .optional(),
  })

type PermissionFormData = z.infer<ReturnType<typeof createPermissionSchema>>

interface PermissionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  permission?: Permission | null
  onSubmit: (data: PermissionFormData) => Promise<void>
  isLoading?: boolean
}

/**
 * Dialog for creating or editing a permission
 */
export function PermissionDialog({
  open,
  onOpenChange,
  permission,
  onSubmit,
  isLoading = false,
}: PermissionDialogProps) {
  const { t } = useTranslation('admin')
  const isEditing = !!permission

  const permissionSchema = createPermissionSchema(t)

  const form = useForm<PermissionFormData>({
    resolver: zodResolver(permissionSchema),
    defaultValues: {
      code: '',
      name: '',
      description: '',
    },
  })

  // Reset form when dialog opens/closes or permission changes
  useEffect(() => {
    if (open) {
      if (permission) {
        form.reset({
          code: permission.code,
          name: permission.name,
          description: permission.description || '',
        })
      } else {
        form.reset({
          code: '',
          name: '',
          description: '',
        })
      }
    }
  }, [open, permission, form])

  const handleSubmit = async (data: PermissionFormData) => {
    await onSubmit(data)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isEditing
              ? t('permissions.editDialog.title')
              : t('permissions.createDialog.title')}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? t('permissions.editDialog.description')
              : t('permissions.createDialog.description')}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(handleSubmit)}
            className="space-y-4"
          >
            <FormField
              control={form.control}
              name="code"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('permissions.form.code')}</FormLabel>
                  <FormControl>
                    <Input
                      placeholder={t('permissions.form.codePlaceholder')}
                      {...field}
                      disabled={isEditing}
                    />
                  </FormControl>
                  <FormDescription>
                    {t('permissions.form.codeDescription')}
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('permissions.form.name')}</FormLabel>
                  <FormControl>
                    <Input
                      placeholder={t('permissions.form.namePlaceholder')}
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>
                    {t('permissions.form.nameDescription')}
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('permissions.form.descriptionLabel')}</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder={t('permissions.form.descriptionPlaceholder')}
                      rows={3}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex justify-end gap-2 pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                {t('permissions.form.cancel')}
              </Button>
              <Button type="submit" disabled={isLoading}>
                {isLoading
                  ? isEditing
                    ? t('permissions.form.saving')
                    : t('permissions.form.creating')
                  : isEditing
                    ? t('permissions.form.save')
                    : t('permissions.form.create')}
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
