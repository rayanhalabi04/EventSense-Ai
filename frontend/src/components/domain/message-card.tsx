import { formatDateTime } from "@/lib/format";
import type { ConversationMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

/** A single chat bubble in the conversation thread (inbound = client, outbound = team). */
export function MessageCard({ message }: { message: ConversationMessage }) {
  const isInbound = message.direction === "inbound";
  return (
    <div className={cn("flex w-full", isInbound ? "justify-start" : "justify-end")}>
      <div className={cn("max-w-[78%] space-y-1", isInbound ? "items-start" : "items-end")}>
        <div className="flex items-center gap-2 px-1">
          <span className="text-xs font-medium text-muted-foreground">
            {isInbound ? "Client" : "Your team"}
          </span>
          <span className="text-xs text-muted-foreground/70">
            {formatDateTime(message.sent_at)}
          </span>
        </div>
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5 text-sm shadow-card",
            isInbound
              ? "rounded-tl-sm bg-card text-card-foreground border border-border"
              : "rounded-tr-sm bg-primary text-primary-foreground",
          )}
        >
          <p className="whitespace-pre-wrap leading-relaxed">{message.body}</p>
        </div>
      </div>
    </div>
  );
}
