import { type Column, DataTable } from "@/components/common/data-table";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useAuditLogs } from "@/hooks/queries";
import { ApiError } from "@/lib/api";
import { formatDateTime, humanize } from "@/lib/format";
import type { AuditLog } from "@/lib/types";
import { Lock, ScrollText, Search } from "lucide-react";
import { useMemo, useState } from "react";

function actorLabel(log: AuditLog): string {
  if (!log.actor_user_id) return "System / AI";
  return `User ${log.actor_user_id.slice(0, 8)}`;
}

function summarizeDetails(details: Record<string, unknown>): string {
  const entries = Object.entries(details).filter(
    ([key]) => !["tenant_id", "user_id", "actor_user_id"].includes(key),
  );
  if (entries.length === 0) return "—";
  return entries
    .slice(0, 3)
    .map(([key, value]) => `${humanize(key)}: ${String(value)}`)
    .join(" · ");
}

export function AuditLogsPage() {
  const { data, isLoading, isError, error, refetch } = useAuditLogs(300);
  const [search, setSearch] = useState("");

  const logs = useMemo(() => {
    const all = data ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return all;
    return all.filter(
      (log) =>
        log.event_type.toLowerCase().includes(q) ||
        (log.resource_type ?? "").toLowerCase().includes(q) ||
        JSON.stringify(log.details).toLowerCase().includes(q),
    );
  }, [data, search]);

  const isForbidden = error instanceof ApiError && error.status === 403;

  const columns: Column<AuditLog>[] = [
    {
      key: "event",
      header: "Action",
      cell: (row) => (
        <div className="flex items-center gap-2">
          <ScrollText className="h-4 w-4 text-muted-foreground" />
          <span className="font-medium text-foreground">{humanize(row.event_type)}</span>
        </div>
      ),
    },
    {
      key: "actor",
      header: "Actor",
      cell: (row) => <span className="text-sm text-muted-foreground">{actorLabel(row)}</span>,
    },
    {
      key: "resource",
      header: "Resource",
      cell: (row) =>
        row.resource_type ? (
          <Badge variant="muted">{humanize(row.resource_type)}</Badge>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "details",
      header: "Details",
      className: "max-w-[24rem]",
      cell: (row) => (
        <span className="truncate text-sm text-muted-foreground">
          {summarizeDetails(row.details)}
        </span>
      ),
    },
    {
      key: "time",
      header: "When",
      headClassName: "text-right",
      className: "whitespace-nowrap text-right text-sm text-muted-foreground",
      cell: (row) => formatDateTime(row.created_at),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Audit logs"
        description="A transparent record of AI and staff actions across your workspace."
        actions={data ? <Badge variant="secondary">{logs.length} events</Badge> : null}
      />

      {isForbidden ? (
        <EmptyState
          icon={Lock}
          title="Manager access required"
          description="Audit logs are available to managers and administrators only."
        />
      ) : isLoading ? (
        <LoadingState rows={6} />
      ) : isError ? (
        <ErrorState description="We couldn't load audit logs." onRetry={refetch} />
      ) : (
        <>
          <div className="relative sm:max-w-sm">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search events…"
              className="pl-9"
              aria-label="Search audit logs"
            />
          </div>
          <DataTable
            columns={columns}
            rows={logs}
            rowKey={(row) => row.id}
            emptyState={
              <EmptyState
                icon={ScrollText}
                title="No audit events"
                description="Actions taken in the workspace will be recorded here."
              />
            }
          />
        </>
      )}
    </div>
  );
}
