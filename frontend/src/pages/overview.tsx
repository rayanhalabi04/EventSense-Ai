import { IntentBadge } from "@/components/badges/intent-badge";
import { RiskBadge } from "@/components/badges/risk-badge";
import { StatCard } from "@/components/common/stat-card";
import { EmptyState, ErrorState } from "@/components/common/states";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useEscalations, useInbox, useInboxSummary, useTasks } from "@/hooks/queries";
import { useAuth } from "@/hooks/use-auth";
import { formatRelative } from "@/lib/format";
import type { InboxItem } from "@/lib/types";
import {
  ArrowRight,
  ClipboardList,
  Inbox as InboxIcon,
  MessageSquare,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

function riskDistribution(items: InboxItem[]) {
  const counts = { high: 0, medium: 0, low: 0, none: 0 };
  for (const item of items) {
    const level = item.risk_level?.toLowerCase();
    if (level === "high") counts.high += 1;
    else if (level === "medium") counts.medium += 1;
    else if (level === "low") counts.low += 1;
    else counts.none += 1;
  }
  return counts;
}

export function OverviewPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const summary = useInboxSummary();
  const openTasks = useTasks({ status: "open" });
  const openEscalations = useEscalations({ status: "open" });
  const recent = useInbox({ page: 1, page_size: 50 });

  const items = recent.data?.items ?? [];
  const dist = riskDistribution(items);
  const distTotal = items.length || 1;
  const segments = [
    { key: "high", label: "High", value: dist.high, className: "bg-destructive" },
    { key: "medium", label: "Medium", value: dist.medium, className: "bg-warning" },
    { key: "low", label: "Low", value: dist.low, className: "bg-success" },
    { key: "none", label: "Unassessed", value: dist.none, className: "bg-muted-foreground/30" },
  ];
  const firstName = user?.full_name?.split(" ")[0] ?? "there";

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Welcome back, ${firstName}`}
        description="Here's what needs your team's attention across client conversations today."
        actions={
          <Button asChild>
            <Link to="/inbox">
              <InboxIcon /> Open inbox
            </Link>
          </Button>
        }
      />

      {/* Summary cards */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Open conversations"
          value={summary.data?.total_open ?? 0}
          icon={MessageSquare}
          hint="Across all clients"
          loading={summary.isLoading}
        />
        <StatCard
          label="High-risk messages"
          value={summary.data?.high_risk ?? 0}
          icon={ShieldAlert}
          tone="danger"
          hint="Need review"
          loading={summary.isLoading}
        />
        <StatCard
          label="Open tasks"
          value={openTasks.data?.length ?? 0}
          icon={ClipboardList}
          hint="Follow-ups to complete"
          loading={openTasks.isLoading}
        />
        <StatCard
          label="Open escalations"
          value={openEscalations.data?.length ?? 0}
          icon={ShieldAlert}
          tone="warning"
          hint="Awaiting manager review"
          loading={openEscalations.isLoading}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Recent activity */}
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">Recent client messages</CardTitle>
            <Button asChild variant="ghost" size="sm">
              <Link to="/inbox">
                View all <ArrowRight />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {recent.isLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: skeleton list
                  <Skeleton key={i} className="h-14 w-full" />
                ))}
              </div>
            ) : recent.isError ? (
              <ErrorState description="Could not load recent messages." onRetry={recent.refetch} />
            ) : items.length === 0 ? (
              <EmptyState
                icon={InboxIcon}
                title="No messages yet"
                description="New client messages will appear here as they arrive."
              />
            ) : (
              <ul className="divide-y divide-border">
                {items.slice(0, 6).map((item) => (
                  <li key={item.conversation_id}>
                    <button
                      type="button"
                      onClick={() => navigate(`/inbox/${item.conversation_id}`)}
                      className="flex w-full items-center gap-3 py-3 text-left transition-colors hover:bg-muted/40"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate text-sm font-medium text-foreground">
                            {item.client_name}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {formatRelative(item.latest_message_at)}
                          </span>
                        </div>
                        <p className="truncate text-sm text-muted-foreground">
                          {item.latest_message_preview ?? "—"}
                        </p>
                      </div>
                      <div className="hidden shrink-0 items-center gap-2 sm:flex">
                        <IntentBadge label={item.intent_label} />
                        <RiskBadge level={item.risk_level} showIcon={false} />
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Risk overview */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Risk overview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Distribution across the {items.length} most recent conversations.
            </p>
            <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted">
              {segments.map((seg) =>
                seg.value > 0 ? (
                  <div
                    key={seg.key}
                    className={seg.className}
                    style={{ width: `${(seg.value / distTotal) * 100}%` }}
                  />
                ) : null,
              )}
            </div>
            <ul className="space-y-2">
              {segments.map((seg) => (
                <li key={seg.key} className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2 text-muted-foreground">
                    <span className={`h-2.5 w-2.5 rounded-full ${seg.className}`} />
                    {seg.label}
                  </span>
                  <span className="font-medium text-foreground">{seg.value}</span>
                </li>
              ))}
            </ul>
            <div className="rounded-lg border border-accent/40 bg-secondary/40 p-3">
              <p className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <Sparkles className="h-3.5 w-3.5" /> AI assists, staff decides
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Every reply is reviewed by your team before it reaches a client.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
