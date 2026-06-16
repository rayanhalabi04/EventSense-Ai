import { formatDateTime, humanize } from "@/lib/format";
import type { AuditEvent } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  Bot,
  CheckCircle2,
  FileText,
  type LucideIcon,
  MessageSquare,
  ShieldAlert,
  Sparkles,
  UserCog,
} from "lucide-react";

interface AuditTimelineProps {
  events: Pick<AuditEvent, "id" | "event_type" | "created_at" | "details" | "resource_type">[];
  className?: string;
}

function iconFor(eventType: string): { icon: LucideIcon; tone: string } {
  const t = eventType.toLowerCase();
  if (t.includes("escalat"))
    return { icon: ShieldAlert, tone: "text-destructive bg-destructive/10" };
  if (t.includes("reply") || t.includes("suggest"))
    return { icon: Sparkles, tone: "text-accent-foreground bg-accent/40" };
  if (t.includes("task")) return { icon: CheckCircle2, tone: "text-success bg-success/12" };
  if (t.includes("message")) return { icon: MessageSquare, tone: "text-primary bg-secondary" };
  if (t.includes("document") || t.includes("rag"))
    return { icon: FileText, tone: "text-primary bg-secondary" };
  if (t.includes("classif") || t.includes("risk") || t.includes("intent"))
    return { icon: Bot, tone: "text-primary bg-secondary" };
  return { icon: UserCog, tone: "text-muted-foreground bg-muted" };
}

/** Readable, human-facing timeline of AI and staff actions. */
export function AuditTimeline({ events, className }: AuditTimelineProps) {
  return (
    <ol className={cn("relative space-y-5", className)}>
      {events.map((event, idx) => {
        const { icon: Icon, tone } = iconFor(event.event_type);
        const isLast = idx === events.length - 1;
        return (
          <li key={event.id} className="relative flex gap-3">
            {!isLast ? (
              <span className="absolute left-[15px] top-8 h-[calc(100%-4px)] w-px bg-border" />
            ) : null}
            <span
              className={cn(
                "z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
                tone,
              )}
            >
              <Icon className="h-4 w-4" />
            </span>
            <div className="min-w-0 pt-0.5">
              <p className="text-sm font-medium text-foreground">{humanize(event.event_type)}</p>
              <p className="text-xs text-muted-foreground">{formatDateTime(event.created_at)}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
