import { IntentBadge } from "@/components/badges/intent-badge";
import { RiskBadge } from "@/components/badges/risk-badge";
import { StatusBadge } from "@/components/badges/status-badge";
import { ActionButton } from "@/components/common/action-button";
import { ErrorState, LoadingState } from "@/components/common/states";
import { AgentAnalysisCard } from "@/components/domain/agent-analysis-card";
import { AIReplyCard } from "@/components/domain/ai-reply-card";
import { AuditTimeline } from "@/components/domain/audit-timeline";
import { MessageCard } from "@/components/domain/message-card";
import { SourceCard } from "@/components/domain/source-card";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { toast } from "@/components/ui/sonner";
import { Textarea } from "@/components/ui/textarea";
import {
  useConversation,
  useCreateEscalation,
  useCreateTask,
  useGenerateReply,
  useRunAgentAnalysis,
  useUpdateConversation,
  useUpdateReply,
} from "@/hooks/queries";
import { formatConfidence, formatDateTime, humanize } from "@/lib/format";
import {
  ArrowLeft,
  CheckCircle2,
  ClipboardList,
  FileText,
  MessageSquare,
  ShieldAlert,
} from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";

export function MessageDetailPage() {
  const { conversationId = "" } = useParams();
  const { data, isLoading, isError, refetch } = useConversation(conversationId);

  const generate = useGenerateReply(conversationId);
  const updateReply = useUpdateReply(conversationId);
  const updateConversation = useUpdateConversation(conversationId);
  const agent = useRunAgentAnalysis(conversationId);

  const [taskOpen, setTaskOpen] = useState(false);
  const [escalateOpen, setEscalateOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <BackLink />
        <LoadingState rows={5} />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="space-y-6">
        <BackLink />
        <ErrorState
          title="Conversation not found"
          description="This conversation may have been removed or you may not have access."
          onRetry={refetch}
        />
      </div>
    );
  }

  const reply = data.suggested_reply;
  const latestMessageId = data.latest_inbound_message?.id ?? null;
  const isHighRisk = data.latest_risk_level?.toLowerCase() === "high";

  const onApprove = (text: string) => {
    if (!reply) return;
    updateReply.mutate(
      { replyId: reply.id, status: "approved", suggested_text: text },
      {
        onSuccess: () => toast.success("Reply approved"),
        onError: (e) => toast.error(e instanceof Error ? e.message : "Could not approve reply"),
      },
    );
  };

  const onSaveEdit = (text: string) => {
    if (!reply) return;
    updateReply.mutate(
      { replyId: reply.id, status: "edited", suggested_text: text },
      {
        onSuccess: () => toast.success("Reply updated"),
        onError: (e) => toast.error(e instanceof Error ? e.message : "Could not save reply"),
      },
    );
  };

  const onReject = () => {
    if (!reply) return;
    updateReply.mutate(
      { replyId: reply.id, status: "rejected" },
      {
        onSuccess: () => toast("Reply rejected"),
        onError: (e) => toast.error(e instanceof Error ? e.message : "Could not reject reply"),
      },
    );
  };

  return (
    <div className="space-y-6">
      <BackLink />

      <PageHeader
        title={data.client_name}
        description={data.client_contact ?? "Client conversation"}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <ActionButton
              icon={ClipboardList}
              label="Create follow-up task"
              variant="outline"
              size="sm"
              onClick={() => setTaskOpen(true)}
            />
            <ActionButton
              icon={ShieldAlert}
              label="Escalate to manager"
              variant={isHighRisk ? "destructive" : "outline"}
              size="sm"
              onClick={() => setEscalateOpen(true)}
            />
            <ActionButton
              icon={CheckCircle2}
              label="Mark as resolved"
              variant="ghost"
              size="sm"
              loading={updateConversation.isPending}
              disabled={data.conversation_status === "closed"}
              onClick={() =>
                updateConversation.mutate(
                  { status: "closed" },
                  {
                    onSuccess: () => toast.success("Conversation marked as resolved"),
                    onError: (e) =>
                      toast.error(
                        e instanceof Error ? e.message : "Could not mark conversation resolved",
                      ),
                  },
                )
              }
            />
          </div>
        }
      />

      {/* AI assessment summary */}
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={data.conversation_status} />
        <IntentBadge
          label={data.latest_intent_label}
          confidence={data.latest_intent_confidence}
          showConfidence
        />
        <RiskBadge level={data.latest_risk_level} />
        {data.latest_classified_at ? (
          <span className="text-xs text-muted-foreground">
            Classified {formatDateTime(data.latest_classified_at)}
          </span>
        ) : null}
      </div>

      {isHighRisk ? (
        <div className="flex items-start gap-3 rounded-lg border border-destructive/25 bg-destructive/[0.06] px-4 py-3">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
          <div>
            <p className="text-sm font-semibold text-destructive">High-risk conversation</p>
            <p className="text-sm text-foreground/80">
              {data.latest_risk_reason ?? "This conversation was flagged as high risk."} Consider
              escalating to a manager.
            </p>
          </div>
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        {/* Left: conversation + AI reply */}
        <div className="space-y-6">
          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle className="flex items-center gap-2 text-base">
                <MessageSquare className="h-4 w-4 text-muted-foreground" /> Conversation
              </CardTitle>
              <Badge variant="muted">{data.messages.length} messages</Badge>
            </CardHeader>
            <CardContent className="max-h-[28rem] space-y-4 overflow-y-auto scrollbar-thin">
              {data.messages.map((message) => (
                <MessageCard key={message.id} message={message} />
              ))}
            </CardContent>
          </Card>

          <AIReplyCard
            reply={reply}
            generating={generate.isPending}
            saving={updateReply.isPending}
            onGenerate={() =>
              generate.mutate(latestMessageId ?? undefined, {
                onSuccess: () => toast.success("Suggested reply generated"),
                onError: (e) =>
                  toast.error(e instanceof Error ? e.message : "Could not generate reply"),
              })
            }
            onApprove={onApprove}
            onSaveEdit={onSaveEdit}
            onReject={onReject}
          />

          <AgentAnalysisCard
            decision={agent.data}
            running={agent.isPending}
            disabled={!latestMessageId}
            onRun={() => {
              if (!latestMessageId) return;
              agent.mutate(latestMessageId, {
                onError: (e) =>
                  toast.error(e instanceof Error ? e.message : "Could not run agent analysis"),
              });
            }}
          />
        </div>

        {/* Right: risk, sources, tasks, escalations, timeline */}
        <div className="space-y-6">
          {data.latest_risk_reason ? (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Risk reason</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <p className="text-sm text-foreground/90">{data.latest_risk_reason}</p>
                {data.latest_risk_flags?.length ? (
                  <div className="flex flex-wrap gap-1.5">
                    {data.latest_risk_flags.map((flag) => (
                      <Badge key={flag} variant="outline">
                        {humanize(flag)}
                      </Badge>
                    ))}
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <FileText className="h-4 w-4 text-muted-foreground" /> Retrieved sources
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {data.rag_sources.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No tenant documents were retrieved for this conversation yet.
                </p>
              ) : (
                data.rag_sources.map((source, i) => (
                  <SourceCard key={`${source.document_id}-${i}`} source={source} />
                ))
              )}
            </CardContent>
          </Card>

          {data.tasks.length > 0 ? (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Follow-up tasks</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {data.tasks.map((task) => (
                  <div
                    key={task.id}
                    className="flex items-center justify-between gap-2 rounded-md border border-border bg-muted/30 px-3 py-2"
                  >
                    <span className="truncate text-sm text-foreground">{task.title}</span>
                    <StatusBadge status={task.status} />
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}

          {data.escalations.length > 0 ? (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Escalations</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {data.escalations.map((esc) => (
                  <div
                    key={esc.id}
                    className="flex items-center justify-between gap-2 rounded-md border border-border bg-muted/30 px-3 py-2"
                  >
                    <span className="truncate text-sm text-foreground">
                      {esc.ai_summary ?? "Escalated for review"}
                    </span>
                    <StatusBadge status={esc.status} />
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}

          {data.audit_timeline.length > 0 ? (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Activity</CardTitle>
              </CardHeader>
              <CardContent>
                <AuditTimeline events={data.audit_timeline} />
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>

      <CreateTaskDialog
        open={taskOpen}
        onOpenChange={setTaskOpen}
        conversationId={conversationId}
        messageId={latestMessageId}
        defaultTitle={`Follow up with ${data.client_name}`}
      />
      <EscalateDialog
        open={escalateOpen}
        onOpenChange={setEscalateOpen}
        conversationId={conversationId}
        messageId={latestMessageId}
        defaultSummary={data.latest_risk_reason ?? ""}
        riskNote={
          data.latest_risk_level
            ? `${humanize(data.latest_risk_level)} risk · ${formatConfidence(
                data.latest_intent_confidence,
              )} intent confidence`
            : undefined
        }
      />
    </div>
  );
}

function BackLink() {
  return (
    <Button asChild variant="ghost" size="sm" className="-ml-2 w-fit text-muted-foreground">
      <Link to="/inbox">
        <ArrowLeft /> Back to inbox
      </Link>
    </Button>
  );
}

function CreateTaskDialog({
  open,
  onOpenChange,
  conversationId,
  messageId,
  defaultTitle,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  conversationId: string;
  messageId: string | null;
  defaultTitle: string;
}) {
  const create = useCreateTask(conversationId);
  const [title, setTitle] = useState(defaultTitle);
  const [description, setDescription] = useState("");
  const [dueAt, setDueAt] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate(
      {
        conversation_id: conversationId,
        message_id: messageId,
        title: title.trim(),
        description: description.trim() || null,
        due_at: dueAt ? new Date(dueAt).toISOString() : null,
      },
      {
        onSuccess: () => {
          toast.success("Follow-up task created");
          onOpenChange(false);
          setDescription("");
          setDueAt("");
        },
        onError: (err) => toast.error(err instanceof Error ? err.message : "Could not create task"),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create follow-up task</DialogTitle>
          <DialogDescription>
            Track an action your team needs to take for this client.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="task-title">Title</Label>
            <Input
              id="task-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="task-desc">Description</Label>
            <Textarea
              id="task-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional details…"
              rows={3}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="task-due">Due date</Label>
            <Input
              id="task-due"
              type="datetime-local"
              value={dueAt}
              onChange={(e) => setDueAt(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending} disabled={!title.trim()}>
              Create task
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function EscalateDialog({
  open,
  onOpenChange,
  conversationId,
  messageId,
  defaultSummary,
  riskNote,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  conversationId: string;
  messageId: string | null;
  defaultSummary: string;
  riskNote?: string;
}) {
  const create = useCreateEscalation(conversationId);
  const [summary, setSummary] = useState(defaultSummary);
  const [nextStep, setNextStep] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate(
      {
        conversation_id: conversationId,
        message_id: messageId,
        ai_summary: summary.trim() || null,
        suggested_next_step: nextStep.trim() || null,
      },
      {
        onSuccess: () => {
          toast.success("Escalated to manager");
          onOpenChange(false);
          setNextStep("");
        },
        onError: (err) => toast.error(err instanceof Error ? err.message : "Could not escalate"),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Escalate to manager</DialogTitle>
          <DialogDescription>
            Send this conversation to a manager's review queue.
            {riskNote ? (
              <span className="mt-1 block font-medium text-foreground">{riskNote}</span>
            ) : null}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="esc-summary">Summary</Label>
            <Textarea
              id="esc-summary"
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="Why does this need a manager's attention?"
              rows={3}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="esc-next">Suggested next step</Label>
            <Input
              id="esc-next"
              value={nextStep}
              onChange={(e) => setNextStep(e.target.value)}
              placeholder="Optional"
            />
          </div>
          <Separator />
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="destructive" loading={create.isPending}>
              <ShieldAlert /> Escalate
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
