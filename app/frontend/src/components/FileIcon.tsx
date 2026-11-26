import {
  FileText,
  Image,
  Video,
  Music,
  FileArchive,
  FileSpreadsheet,
  Presentation,
  File,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface FileIconProps {
  contentType?: string
  extension?: string | null
  className?: string
  size?: 'sm' | 'md' | 'lg'
}

const sizeClasses = {
  sm: 'h-4 w-4',
  md: 'h-6 w-6',
  lg: 'h-10 w-10',
}

export function FileIcon({ contentType, extension, className, size = 'md' }: FileIconProps) {
  const iconClass = cn(sizeClasses[size], className)

  // Check by content type first
  if (contentType) {
    if (contentType.startsWith('image/')) {
      return <Image className={cn(iconClass, 'text-green-600 dark:text-green-400')} />
    }
    if (contentType.startsWith('video/')) {
      return <Video className={cn(iconClass, 'text-purple-600 dark:text-purple-400')} />
    }
    if (contentType.startsWith('audio/')) {
      return <Music className={cn(iconClass, 'text-pink-600 dark:text-pink-400')} />
    }
    if (contentType === 'application/pdf') {
      return <FileText className={cn(iconClass, 'text-red-600 dark:text-red-400')} />
    }
    if (
      contentType.includes('spreadsheet') ||
      contentType.includes('excel') ||
      contentType === 'text/csv'
    ) {
      return <FileSpreadsheet className={cn(iconClass, 'text-green-700 dark:text-green-300')} />
    }
    if (contentType.includes('presentation') || contentType.includes('powerpoint')) {
      return <Presentation className={cn(iconClass, 'text-orange-600 dark:text-orange-400')} />
    }
    if (contentType.includes('word') || contentType === 'text/plain') {
      return <FileText className={cn(iconClass, 'text-blue-600 dark:text-blue-400')} />
    }
    if (contentType.includes('zip') || contentType.includes('archive') || contentType.includes('compressed')) {
      return <FileArchive className={cn(iconClass, 'text-yellow-600 dark:text-yellow-400')} />
    }
  }

  // Fallback to extension
  const ext = extension?.toLowerCase()
  if (ext) {
    if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico'].includes(ext)) {
      return <Image className={cn(iconClass, 'text-green-600 dark:text-green-400')} />
    }
    if (['mp4', 'mov', 'avi', 'webm', 'mkv', 'flv'].includes(ext)) {
      return <Video className={cn(iconClass, 'text-purple-600 dark:text-purple-400')} />
    }
    if (['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'].includes(ext)) {
      return <Music className={cn(iconClass, 'text-pink-600 dark:text-pink-400')} />
    }
    if (ext === 'pdf') {
      return <FileText className={cn(iconClass, 'text-red-600 dark:text-red-400')} />
    }
    if (['xls', 'xlsx', 'csv'].includes(ext)) {
      return <FileSpreadsheet className={cn(iconClass, 'text-green-700 dark:text-green-300')} />
    }
    if (['ppt', 'pptx'].includes(ext)) {
      return <Presentation className={cn(iconClass, 'text-orange-600 dark:text-orange-400')} />
    }
    if (['doc', 'docx', 'txt', 'rtf', 'md'].includes(ext)) {
      return <FileText className={cn(iconClass, 'text-blue-600 dark:text-blue-400')} />
    }
    if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) {
      return <FileArchive className={cn(iconClass, 'text-yellow-600 dark:text-yellow-400')} />
    }
  }

  return <File className={cn(iconClass, 'text-muted-foreground')} />
}
