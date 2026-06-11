import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

interface DemoMetricCardProps {
  title: string;
  icon: LucideIcon;
  metric: string;
  caption?: string;
  status?: "pass" | "warn" | "info";
  children?: React.ReactNode;
}

const STATUS_STYLES = {
  pass: "text-success",
  warn: "text-[hsl(33_75%_32%)]",
  info: "text-foreground",
} as const;

/** Presentation-ready metric card for the Evaluation/Demo page. */
export function DemoMetricCard({
  title,
  icon: Icon,
  metric,
  caption,
  status = "info",
  children,
}: DemoMetricCardProps) {
  return (
    <Card>
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
          <Icon className="h-4 w-4" />
        </span>
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className={cn("text-3xl font-semibold tracking-tight", STATUS_STYLES[status])}>
          {metric}
        </p>
        {caption ? <p className="mt-1 text-xs text-muted-foreground">{caption}</p> : null}
        {children ? <div className="mt-3">{children}</div> : null}
      </CardContent>
    </Card>
  );
}
