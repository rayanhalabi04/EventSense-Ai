import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: number | string;
  icon: LucideIcon;
  hint?: string;
  /** Highlight tone for attention-grabbing metrics (e.g. high risk). */
  tone?: "default" | "danger" | "warning" | "success";
  loading?: boolean;
}

const TONE_STYLES: Record<NonNullable<StatCardProps["tone"]>, { icon: string; ring: string }> = {
  default: { icon: "bg-secondary text-secondary-foreground", ring: "" },
  danger: { icon: "bg-destructive/12 text-destructive", ring: "ring-1 ring-destructive/20" },
  warning: { icon: "bg-warning/15 text-[hsl(33_75%_32%)]", ring: "" },
  success: { icon: "bg-success/12 text-success", ring: "" },
};

export function StatCard({
  label,
  value,
  icon: Icon,
  hint,
  tone = "default",
  loading = false,
}: StatCardProps) {
  const styles = TONE_STYLES[tone];
  return (
    <Card className={cn("p-5", styles.ring)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-muted-foreground">{label}</p>
          {loading ? (
            <Skeleton className="mt-2 h-8 w-16" />
          ) : (
            <p className="mt-1 text-3xl font-semibold tracking-tight text-foreground">{value}</p>
          )}
          {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
        </div>
        <span className={cn("flex h-10 w-10 items-center justify-center rounded-lg", styles.icon)}>
          <Icon className="h-5 w-5" />
        </span>
      </div>
    </Card>
  );
}
