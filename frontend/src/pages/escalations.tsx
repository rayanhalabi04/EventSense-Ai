import { IntentBadge } from "@/components/badges/intent-badge";
import { RiskBadge } from "@/components/badges/risk-badge";
import { StatusBadge } from "@/components/badges/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { toast } from "@/components/ui/sonner";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useEscalations, useUpdateEscalation } from "@/hooks/queries";
import { useAuth } from "@/hooks/use-auth";
import { formatDateTime } from "@/lib/format";
import type { Escalation } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ArrowUpRight, ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

const TAB_OPTIONS = [
  { value: "all", label: "All" },
  { value: "open", label: "Open" },
  { value: "in_review", label: "In review" },
  { value: "resolved", label: "Resolved" },
];

export function EscalationsPage() {
  const { user } = useAuth();
  const isManager = user?.role === "manager" || user?.role === "platform_admin";
  const [tab, setTab] = useState("all");
  const { data, isLoading, isError, refetch } = useEscalations(
    tab === "all" ? {} : { status: tab },
  );
  const update = useUpdateEscalation();

  const escalations = data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Escalations"
        description="Risky conversations sent to a manager for review and a decision."
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          {TAB_OPTIONS.map((opt) => (
            <TabsTrigger key={opt.value} value={opt.value}>
              {opt.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {isLoading ? (
        <LoadingState rows={3} />
      ) : isError ? (
        <ErrorState description="We couldn't load escalations." onRetry={refetch} />
      ) : escalations.length === 0 ? (
        <EmptyState
          icon={ShieldCheck}
          title="Nothing to review"
          description="When staff escalate a risky conversation, it lands here for a manager to action."
        />
      ) : (
        <div className="space-y-3">
          {escalations.map((esc) => (
            <EscalationRow
              key={esc.id}
              escalation={esc}
              canManage={isManager}
              onSetStatus={(status) =>
                update.mutate(
                  { escalationId: esc.id, status },
                  {
                    onSuccess: () => toast.success("Escalation updated"),
                    onError: (e) =>
                      toast.error(e instanceof Error ? e.message : "Could not update"),
                  },
                )
              }
              updating={update.isPending}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function EscalationRow({
  escalation,
  canManage,
  onSetStatus,
  updating,
}: {
  escalation: Escalation;
  canManage: boolean;
  onSetStatus: (status: Escalation["status"]) => void;
  updating: boolean;
}) {
  const isHigh = escalation.risk_level?.toLowerCase() === "high";
  return (
    <Card className={cn(isHigh && "border-l-4 border-l-destructive")}>
      <CardContent className="p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={escalation.status} />
              <RiskBadge level={escalation.risk_level} />
              <IntentBadge label={escalation.intent_label} />
              <span className="text-xs text-muted-foreground">
                {formatDateTime(escalation.created_at)}
              </span>
            </div>

            <div>
              <p className="text-sm font-medium text-foreground">
                {escalation.ai_summary ?? "Escalated for manager review"}
              </p>
              {escalation.risk_reason ? (
                <p className="mt-1 flex items-start gap-1.5 text-sm text-muted-foreground">
                  <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
                  {escalation.risk_reason}
                </p>
              ) : null}
            </div>

            {escalation.suggested_next_step ? (
              <div className="rounded-md border border-accent/40 bg-secondary/40 px-3 py-2">
                <p className="text-xs font-medium text-muted-foreground">Suggested next step</p>
                <p className="text-sm text-foreground">{escalation.suggested_next_step}</p>
              </div>
            ) : null}
          </div>

          <div className="flex shrink-0 flex-col items-stretch gap-2 lg:w-48">
            <Button asChild variant="outline" size="sm">
              <Link to={`/inbox/${escalation.conversation_id}`}>
                Open conversation <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
            {canManage ? (
              <>
                <Separator />
                {escalation.status !== "in_review" && escalation.status !== "resolved" ? (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => onSetStatus("in_review")}
                    loading={updating}
                  >
                    Start review
                  </Button>
                ) : null}
                {escalation.status !== "resolved" ? (
                  <Button size="sm" onClick={() => onSetStatus("resolved")} loading={updating}>
                    <ShieldCheck /> Mark resolved
                  </Button>
                ) : null}
              </>
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
