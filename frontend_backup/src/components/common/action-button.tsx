import { Button, type ButtonProps } from "@/components/ui/button";
import type { LucideIcon } from "lucide-react";

interface ActionButtonProps extends ButtonProps {
  icon?: LucideIcon;
  label: string;
}

/**
 * Labelled action button with an optional leading icon.
 * Used for the staff actions on the message detail page and elsewhere.
 */
export function ActionButton({ icon: Icon, label, ...props }: ActionButtonProps) {
  return (
    <Button {...props}>
      {Icon ? <Icon /> : null}
      {label}
    </Button>
  );
}
