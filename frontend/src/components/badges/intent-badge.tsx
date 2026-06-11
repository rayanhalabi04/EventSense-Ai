import { Badge } from "@/components/ui/badge";
import { formatConfidence, humanize } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Sparkles } from "lucide-react";

interface IntentBadgeProps {
  label: string | null | undefined;
  confidence?: number | null;
  className?: string;
  showConfidence?: boolean;
}

export function IntentBadge({
  label,
  confidence,
  className,
  showConfidence = false,
}: IntentBadgeProps) {
  if (!label) {
    return (
      <Badge variant="muted" className={className}>
        Not classified
      </Badge>
    );
  }
  return (
    <Badge variant="accent" className={cn(className)}>
      <Sparkles className="h-3 w-3" />
      {humanize(label)}
      {showConfidence && confidence != null ? (
        <span className="ml-0.5 font-normal opacity-70">{formatConfidence(confidence)}</span>
      ) : null}
    </Badge>
  );
}
