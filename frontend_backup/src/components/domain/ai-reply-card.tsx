import { StatusBadge } from "@/components/badges/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/sonner";
import { Textarea } from "@/components/ui/textarea";
import { humanize } from "@/lib/format";
import type { SuggestedReply } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Check, Copy, Pencil, ShieldCheck, Sparkles, TriangleAlert, X } from "lucide-react";
import { useEffect, useState } from "react";

interface AIReplyCardProps {
  reply: SuggestedReply | null;
  generating?: boolean;
  saving?: boolean;
  onGenerate: () => void;
  onApprove: (text: string) => void;
  onSaveEdit: (text: string) => void;
  onReject: () => void;
}

export function AIReplyCard({
  reply,
  generating = false,
  saving = false,
  onGenerate,
  onApprove,
  onSaveEdit,
  onReject,
}: AIReplyCardProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(reply?.suggested_text ?? "");

  // Keep the editable draft in sync when a new reply arrives (by id or text).
  // biome-ignore lint/correctness/useExhaustiveDependencies: reset on reply identity change is intentional
  useEffect(() => {
    setDraft(reply?.suggested_text ?? "");
    setEditing(false);
  }, [reply?.id, reply?.suggested_text]);

  const copy = async () => {
    if (!reply) return;
    await navigator.clipboard.writeText(reply.suggested_text);
    toast.success("Reply copied to clipboard");
  };

  return (
    <Card className="border-accent/50 bg-gradient-to-b from-secondary/40 to-card">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Sparkles className="h-4 w-4" />
          </span>
          Suggested reply
        </CardTitle>
        {reply ? <StatusBadge status={reply.status} /> : null}
      </CardHeader>
      <CardContent className="space-y-4">
        {/* AI-in-control note */}
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <ShieldCheck className="h-3.5 w-3.5 text-success" />
          Drafted by AI. Nothing is sent automatically — review and approve before replying.
        </p>

        {!reply ? (
          <div className="rounded-lg border border-dashed border-border bg-card/60 px-4 py-8 text-center">
            <p className="text-sm text-muted-foreground">
              No suggested reply yet for this conversation.
            </p>
            <Button className="mt-4" onClick={onGenerate} loading={generating}>
              <Sparkles /> Generate suggested reply
            </Button>
          </div>
        ) : (
          <>
            {reply.answer_supported ? (
              <Badge variant="success">
                <ShieldCheck className="h-3 w-3" /> Grounded in tenant documents
              </Badge>
            ) : (
              <div className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2">
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-[hsl(33_75%_32%)]" />
                <p className="text-xs text-[hsl(33_60%_28%)]">
                  Not fully supported by documents
                  {reply.refusal_reason ? `: ${humanize(reply.refusal_reason)}` : "."} Review
                  carefully before approving.
                </p>
              </div>
            )}

            {editing ? (
              <Textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={6}
                className="bg-card"
                aria-label="Edit suggested reply"
              />
            ) : (
              <div className="rounded-lg border border-border bg-card p-4">
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                  {reply.suggested_text}
                </p>
              </div>
            )}

            <div className={cn("flex flex-wrap items-center gap-2")}>
              {editing ? (
                <>
                  <Button
                    size="sm"
                    onClick={() => {
                      onSaveEdit(draft);
                      setEditing(false);
                    }}
                    loading={saving}
                    disabled={!draft.trim()}
                  >
                    <Check /> Save &amp; approve
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setDraft(reply.suggested_text);
                      setEditing(false);
                    }}
                  >
                    Cancel
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    size="sm"
                    onClick={() => onApprove(reply.suggested_text)}
                    loading={saving}
                    disabled={reply.status === "approved"}
                  >
                    <Check /> Approve
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                    <Pencil /> Edit
                  </Button>
                  <Button size="sm" variant="outline" onClick={copy}>
                    <Copy /> Copy
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive hover:text-destructive"
                    onClick={onReject}
                    disabled={reply.status === "rejected"}
                  >
                    <X /> Reject
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="ml-auto"
                    onClick={onGenerate}
                    loading={generating}
                  >
                    <Sparkles /> Regenerate
                  </Button>
                </>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
