import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { humanize } from "@/lib/format";
import type { AgentDecision } from "@/lib/types";
import { Bot, CheckCircle2, MinusCircle } from "lucide-react";

interface AgentAnalysisCardProps {
  decision: AgentDecision | undefined;
  running: boolean;
  disabled: boolean;
  onRun: () => void;
}

/**
 * Dry-run focused-agent analysis. The agent only runs for risky/complex intents
 * and never creates tasks or escalations from here — this card shows the
 * recommendation only.
 */
export function AgentAnalysisCard({ decision, running, disabled, onRun }: AgentAnalysisCardProps) {
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
          <AgentDecisionView decision={decision} />
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

function AgentDecisionView({ decision }: { decision: AgentDecision }) {
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

      <p className="text-xs text-muted-foreground">
        Recommendation only — no task, escalation, or client message is created from this analysis.
      </p>
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
