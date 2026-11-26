import { useState } from 'react'
import { Avatar, AvatarImage, AvatarFallback } from './avatar'
import { cn } from '@/lib/utils'

interface UserAvatarProps {
  firstName?: string | null
  lastName?: string | null
  avatarUrl?: string | null
  fullImageUrl?: string | null
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const sizeClasses = {
  sm: 'h-6 w-6 text-xs',
  md: 'h-8 w-8 text-sm',
  lg: 'h-10 w-10 text-base',
}

export function UserAvatar({
  firstName,
  lastName,
  avatarUrl,
  size = 'md',
  className,
}: UserAvatarProps) {
  const [imageError, setImageError] = useState(false)

  const getInitials = () => {
    const first = firstName?.charAt(0) || ''
    const last = lastName?.charAt(0) || ''
    return (first + last).toUpperCase() || 'U'
  }

  const shouldShowImage = avatarUrl && !imageError

  return (
    <Avatar className={cn(sizeClasses[size], className)}>
      {shouldShowImage && (
        <AvatarImage
          src={avatarUrl}
          alt={`${firstName} ${lastName}`}
          onError={() => setImageError(true)}
        />
      )}
      <AvatarFallback className={cn('font-medium', size === 'sm' && 'text-xs')}>
        {getInitials()}
      </AvatarFallback>
    </Avatar>
  )
}
