import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { humanize } from "@/lib/format";
import type { AgentApplied, AgentDecision, AgentToolTrace } from "@/lib/types";
import { Bot, CheckCircle2, FileText, MinusCircle, Wand2 } from "lucide-react";

interface AgentAnalysisCardProps {
  decision: AgentDecision | undefined;
  running: boolean;
  disabled: boolean;
  onRun: () => void;
  /** Apply the recommendation (apply=true). */
  onApply: () => void;
  applying: boolean;
  /** Ids returned after a successful apply, if any. */
  applied: AgentApplied | null | undefined;
}

/**
 * Focused-agent analysis. "Run agent analysis" is read-only (apply=false) and
 * shows a recommendation only. When the agent recommends a task and/or
 * escalation, staff can manually "Apply recommendations" (apply=true) to create
 * (or reuse) those records. No client message is ever sent from this card.
 */
export function AgentAnalysisCard({
  decision,
  running,
  disabled,
  onRun,
  onApply,
  applying,
  applied,
}: AgentAnalysisCardProps) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2 text-base">
          <Bot className="h-4 w-4 text-muted-foreground" /> Agent analysis
        </CardTitle>
        <Button size="sm" variant="outline" loading={running} disabled={disabled} onClick={onRun}>
          {decision ? "Re-run analysis" : "Run agent analysis"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {!decision ? (
          <p className="text-sm text-muted-foreground">
            {disabled
              ? "No inbound message to analyze yet."
              : "Run a read-only agent analysis to see recommended next steps. Nothing is created or sent."}
          </p>
        ) : decision.ran ? (
          <AgentDecisionView
            decision={decision}
            onApply={onApply}
            applying={applying}
            applied={applied}
          />
        ) : (
          <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/30 px-4 py-3">
            <MinusCircle className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium text-foreground">
                Agent not needed for this message.
              </p>
              <p className="text-sm text-muted-foreground">
                {decision.skipped_reason
                  ? humanize(decision.skipped_reason)
                  : "This message is not risky or complex enough to need the agent."}
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AgentDecisionView({
  decision,
  onApply,
  applying,
  applied,
}: {
  decision: AgentDecision;
  onApply: () => void;
  applying: boolean;
  applied: AgentApplied | null | undefined;
}) {
  const recommendsAction =
    decision.recommended_task.should_create || decision.recommended_escalation.should_escalate;
  const hasApplied = Boolean(
    applied?.task_id || applied?.escalation_id || applied?.suggested_reply_id,
  );
  const suggestedReplyTool = decision.tools_used.find(
    (tool) => tool.tool_name === "suggest_reply",
  );
  const sourceIds = Array.from(
    new Set(decision.tools_used.flatMap((tool) => tool.source_ids ?? [])),
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="accent">Trigger: {humanize(decision.trigger_intent) || "—"}</Badge>
        <Badge variant={decision.confidence === "high" ? "success" : "warning"}>
          {humanize(decision.confidence)} confidence
        </Badge>
        {decision.risk_level ? (
          <Badge variant="outline">{humanize(decision.risk_level)} risk</Badge>
        ) : null}
      </div>

      <dl className="space-y-2">
        <DecisionRow
          label="Recommend follow-up task"
          value={decision.recommended_task.should_create}
          tone="warning"
        />
        <DecisionRow
          label="Recommend escalation"
          value={decision.recommended_escalation.should_escalate}
          tone="destructive"
        />
        <DecisionRow
          label="Human review required"
          value={decision.human_review_required}
          tone="warning"
        />
      </dl>

      {decision.risk_reason ? (
        <p className="rounded-md border border-border bg-muted/30 px-3 py-2 text-sm text-foreground/90">
          {decision.risk_reason}
        </p>
      ) : null}

      <ToolTraceList tools={decision.tools_used} />

      {sourceIds.length ? (
        <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
          <p className="mb-2 flex items-center gap-2 text-sm font-medium text-foreground">
            <FileText className="h-4 w-4 text-muted-foreground" /> RAG sources
          </p>
          <div className="flex flex-wrap gap-1.5">
            {sourceIds.map((id) => (
              <code
                key={id}
                className="rounded bg-background px-1.5 py-0.5 font-mono text-xs text-muted-foreground"
              >
                {id}
              </code>
            ))}
          </div>
        </div>
      ) : null}

      {suggestedReplyTool?.suggested_reply_preview ? (
        <div className="rounded-md border border-border bg-background px-3 py-2">
          <p className="mb-1 text-sm font-medium text-foreground">
            {applied?.suggested_reply_id ? "Saved draft reply" : "Draft reply preview"}
          </p>
          <p className="whitespace-pre-wrap text-sm text-foreground/90">
            {suggestedReplyTool.suggested_reply_preview}
          </p>
        </div>
      ) : null}

      {recommendsAction ? (
        <div className="space-y-3 rounded-lg border border-border bg-muted/30 px-4 py-3">
          {hasApplied ? (
            <div className="space-y-2">
              <p className="flex items-center gap-2 text-sm font-medium text-foreground">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" /> Recommendations applied
              </p>
              {applied?.task_id ? <AppliedRow label="Task" id={applied.task_id} /> : null}
              {applied?.escalation_id ? (
                <AppliedRow label="Escalation" id={applied.escalation_id} />
              ) : null}
              {applied?.suggested_reply_id ? (
                <AppliedRow label="Draft reply" id={applied.suggested_reply_id} />
              ) : null}
            </div>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-foreground/90">
                Create the recommended {decision.recommended_task.should_create ? "task" : ""}
                {decision.recommended_task.should_create &&
                decision.recommended_escalation.should_escalate
                  ? " and "
                  : ""}
                {decision.recommended_escalation.should_escalate ? "escalation" : ""}.
              </p>
              <Button size="sm" loading={applying} onClick={onApply}>
                <Wand2 className="h-4 w-4" /> Apply recommendations
              </Button>
            </div>
          )}
        </div>
      ) : null}

      <p className="text-xs text-muted-foreground">
        {recommendsAction
          ? "Applying creates draft/review records only. No client message is sent and no reply is approved or sent."
          : "Recommendation only — no task, escalation, or client message is created from this analysis."}
      </p>
    </div>
  );
}

function ToolTraceList({ tools }: { tools: AgentToolTrace[] }) {
  if (!tools.length) {
    return null;
  }
  return (
    <div className="space-y-2">
      {tools.map((tool) => (
        <div
          key={`${tool.tool_name}-${tool.status}-${tool.created_id ?? tool.output_summary ?? ""}`}
          className="flex items-start justify-between gap-3 rounded-md border border-border bg-muted/20 px-3 py-2"
        >
          <div className="min-w-0">
            <p className="text-sm font-medium text-foreground">{humanize(tool.tool_name)}</p>
            <p className="text-sm text-muted-foreground">{tool.summary}</p>
            {tool.output_summary ? (
              <p className="mt-1 text-xs text-muted-foreground">{tool.output_summary}</p>
            ) : null}
          </div>
          <Badge variant={tool.status === "success" ? "success" : "outline"}>
            {humanize(tool.status)}
          </Badge>
        </div>
      ))}
    </div>
  );
}

function AppliedRow({ label, id }: { label: string; id: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-sm text-foreground/90">{label}</span>
      <code className="rounded bg-background px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
        {id}
      </code>
    </div>
  );
}

function DecisionRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: boolean;
  tone: "warning" | "destructive";
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-sm text-foreground/90">{label}</dt>
      <dd>
        {value ? (
          <Badge variant={tone}>
            <CheckCircle2 className="h-3.5 w-3.5" /> Yes
          </Badge>
        ) : (
          <Badge variant="muted">No</Badge>
        )}
      </dd>
    </div>
  );
}
