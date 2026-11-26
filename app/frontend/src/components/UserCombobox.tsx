import * as React from 'react'
import { Check, ChevronsUpDown, User } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'

export interface UserOption {
  id: string
  email?: string | null
  first_name?: string | null
  last_name?: string | null
  phone?: string | null
}

interface UserComboboxProps {
  users: UserOption[]
  value?: string
  onChange?: (value: string) => void
  placeholder?: string
  searchPlaceholder?: string
  emptyMessage?: string
  disabled?: boolean
  isLoading?: boolean
  currentUserId?: string
  className?: string
  requirePhone?: boolean
}

export function UserCombobox({
  users,
  value,
  onChange,
  placeholder,
  searchPlaceholder,
  emptyMessage,
  disabled,
  isLoading,
  currentUserId,
  className,
  requirePhone,
}: UserComboboxProps) {
  const { t } = useTranslation('admin')
  const [open, setOpen] = React.useState(false)

  // Sort users: current user first, then alphabetically by name
  const sortedUsers = React.useMemo(() => {
    return [...users].sort((a, b) => {
      if (currentUserId) {
        if (a.id === currentUserId) return -1
        if (b.id === currentUserId) return 1
      }
      const aName = `${a.first_name ?? ''} ${a.last_name ?? ''}`.toLowerCase()
      const bName = `${b.first_name ?? ''} ${b.last_name ?? ''}`.toLowerCase()
      return aName.localeCompare(bName)
    })
  }, [users, currentUserId])

  const selectedUser = React.useMemo(
    () => users.find((user) => user.id === value),
    [users, value]
  )

  const formatUserDisplay = (user: UserOption) => {
    const name = [user.first_name, user.last_name].filter(Boolean).join(' ')
    if (name && user.email) {
      return `${name} (${user.email})`
    }
    if (name) {
      return name
    }
    return user.email || user.id
  }

  const formatUserLabel = (user: UserOption) => {
    const display = formatUserDisplay(user)
    const parts: string[] = []
    if (currentUserId && user.id === currentUserId) {
      parts.push(t('notifications.send.channelSection.you', 'You'))
    }
    if (requirePhone && !user.phone) {
      parts.push(t('notifications.send.channelSection.noPhone', 'no phone'))
    }
    if (parts.length > 0) {
      return `${display} (${parts.join(', ')})`
    }
    return display
  }

  const isUserDisabled = (user: UserOption) => {
    return requirePhone && !user.phone
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn('w-full justify-between', className)}
          disabled={disabled || isLoading}
        >
          <div className="flex items-center gap-2 truncate">
            <User className="h-4 w-4 shrink-0 opacity-50" />
            {isLoading ? (
              <span className="text-muted-foreground">
                {t('common:common.loading', 'Loading...')}
              </span>
            ) : selectedUser ? (
              <span className="truncate">{formatUserLabel(selectedUser)}</span>
            ) : (
              <span className="text-muted-foreground">
                {placeholder ?? t('notifications.send.channelSection.userPlaceholder', 'Select a user...')}
              </span>
            )}
          </div>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[400px] p-0" align="start">
        <Command>
          <CommandInput
            placeholder={searchPlaceholder ?? t('notifications.send.channelSection.searchUsers', 'Search users...')}
          />
          <CommandList>
            <CommandEmpty>
              {emptyMessage ?? t('notifications.send.channelSection.noUsersFound', 'No users found.')}
            </CommandEmpty>
            <CommandGroup>
              {sortedUsers.map((user) => {
                const userDisabled = isUserDisabled(user)
                return (
                  <CommandItem
                    key={user.id}
                    value={`${user.first_name ?? ''} ${user.last_name ?? ''} ${user.email ?? ''}`}
                    onSelect={() => {
                      if (!userDisabled) {
                        onChange?.(user.id)
                        setOpen(false)
                      }
                    }}
                    disabled={userDisabled}
                    className={userDisabled ? 'opacity-50 cursor-not-allowed' : ''}
                  >
                    <Check
                      className={cn(
                        'mr-2 h-4 w-4',
                        value === user.id ? 'opacity-100' : 'opacity-0'
                      )}
                    />
                    <div className="flex flex-col">
                      <span>{formatUserLabel(user)}</span>
                    </div>
                  </CommandItem>
                )
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
