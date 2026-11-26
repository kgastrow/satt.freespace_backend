"use client"

import * as React from "react"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"

function SidebarContent({ className, children }: React.ComponentProps<"div">) {
  return (
    <ScrollArea
      data-slot="sidebar-content"
      data-sidebar="content"
      className={cn(
        "min-h-0 flex-1 group-data-[collapsible=icon]:overflow-hidden",
        className
      )}
    >
      <div className="flex flex-col gap-2">{children}</div>
    </ScrollArea>
  )
}

export { SidebarContent }
