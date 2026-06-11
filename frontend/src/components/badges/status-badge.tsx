import { Badge, type BadgeProps } from "@/components/ui/badge";
import { humanize } from "@/lib/format";
import type {
  ConversationStatus,
  DocumentStatus,
  EscalationStatus,
  SuggestedReplyStatus,
  TaskStatus,
} from "@/lib/types";

type AnyStatus =
  | ConversationStatus
  | TaskStatus
  | EscalationStatus
  | DocumentStatus
  | SuggestedReplyStatus
  | string;

const VARIANTS: Record<string, BadgeProps["variant"]> = {
  // Conversations
  open: "warning",
  closed: "muted",
  escalated: "destructive",
  // Tasks
  in_progress: "accent",
  completed: "success",
  cancelled: "muted",
  // Escalations
  in_review: "accent",
  resolved: "success",
  // Documents
  active: "success",
  archived: "muted",
  // Suggested replies
  draft: "secondary",
  approved: "success",
  edited: "accent",
  rejected: "destructive",
};

export function StatusBadge({ status, className }: { status: AnyStatus; className?: string }) {
  const variant = VARIANTS[status] ?? "secondary";
  return (
    <Badge variant={variant} className={className}>
      {humanize(status)}
    </Badge>
  );
}
