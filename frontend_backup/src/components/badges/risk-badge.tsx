import { Badge, type BadgeProps } from "@/components/ui/badge";
import type { RiskLevel } from "@/lib/types";
import { cn } from "@/lib/utils";
import { AlertTriangle, ShieldAlert, ShieldCheck } from "lucide-react";

interface RiskBadgeProps {
  level: RiskLevel | null | undefined;
  className?: string;
  showIcon?: boolean;
}

const CONFIG: Record<
  string,
  { label: string; variant: BadgeProps["variant"]; icon: typeof ShieldCheck }
> = {
  high: { label: "High risk", variant: "destructive", icon: ShieldAlert },
  medium: { label: "Medium risk", variant: "warning", icon: AlertTriangle },
  low: { label: "Low risk", variant: "success", icon: ShieldCheck },
};

export function RiskBadge({ level, className, showIcon = true }: RiskBadgeProps) {
  if (!level) {
    return (
      <Badge variant="muted" className={className}>
        Not assessed
      </Badge>
    );
  }
  const config = CONFIG[level.toLowerCase()] ?? {
    label: level,
    variant: "muted" as const,
    icon: ShieldCheck,
  };
  const Icon = config.icon;
  return (
    <Badge variant={config.variant} className={cn(className)}>
      {showIcon ? <Icon className="h-3 w-3" /> : null}
      {config.label}
    </Badge>
  );
}
