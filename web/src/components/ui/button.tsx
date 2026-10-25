import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"
import { Slot } from "radix-ui"

const buttonVariants = cva(
  "notch inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 text-[12px] leading-none whitespace-nowrap transition-colors duration-200 outline-none select-none disabled:pointer-events-none disabled:opacity-40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-ink",
        destructive: "bg-bad text-white hover:bg-ink",
        outline: "border border-ink bg-transparent text-ink hover:bg-ink hover:text-paper",
        secondary: "bg-blue-50 text-primary hover:bg-blue-100",
        ghost: "text-ink hover:bg-blue-50 [clip-path:none]",
        link: "text-primary underline-offset-4 hover:underline [clip-path:none]",
      },
      size: {
        default: "h-9 px-4",
        xs: "h-6 gap-1 px-2 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1.5 px-3",
        lg: "h-11 px-6",
        icon: "size-9",
        "icon-xs": "size-6 [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8",
        "icon-lg": "size-11",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
