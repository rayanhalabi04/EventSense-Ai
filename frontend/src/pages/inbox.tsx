import { IntentBadge } from "@/components/badges/intent-badge";
import { RiskBadge } from "@/components/badges/risk-badge";
import { StatusBadge } from "@/components/badges/status-badge";
import { type Column, DataTable } from "@/components/common/data-table";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useInbox } from "@/hooks/queries";
import { formatRelative, humanize } from "@/lib/format";
import type { InboxItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Inbox as InboxIcon, Search, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

const STATUS_OPTIONS = ["open", "escalated", "closed"];
const RISK_OPTIONS = ["high", "medium", "low"];

export function InboxPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [riskFilter, setRiskFilter] = useState<string>("all");
  const [intentFilter, setIntentFilter] = useState<string>("all");

  const { data, isLoading, isError, refetch } = useInbox({
    status: statusFilter === "all" ? undefined : statusFilter,
    search: search.trim() || undefined,
    page_size: 100,
  });

  const allItems = data?.items ?? [];

  // Intent options are derived from the loaded data (no dedicated backend param).
  const intentOptions = useMemo(() => {
    const set = new Set<string>();
    for (const item of allItems) if (item.intent_label) set.add(item.intent_label);
    return Array.from(set).sort();
  }, [allItems]);

  // Risk + intent are filtered client-side on the loaded page.
  const items = allItems.filter((item) => {
    const riskOk = riskFilter === "all" || item.risk_level?.toLowerCase() === riskFilter;
    const intentOk = intentFilter === "all" || item.intent_label === intentFilter;
    return riskOk && intentOk;
  });

  const hasActiveFilters =
    statusFilter !== "all" ||
    riskFilter !== "all" ||
    intentFilter !== "all" ||
    search.trim() !== "";

  const clearFilters = () => {
    setSearch("");
    setStatusFilter("all");
    setRiskFilter("all");
    setIntentFilter("all");
  };

  const columns: Column<InboxItem>[] = [
    {
      key: "client",
      header: "Client",
      cell: (row) => (
        <div className="flex items-center gap-2">
          {row.has_unread ? (
            <span className="h-2 w-2 shrink-0 rounded-full bg-primary" aria-label="Unread" />
          ) : (
            <span className="h-2 w-2 shrink-0" />
          )}
          <div className="min-w-0">
            <p className="truncate font-medium text-foreground">{row.client_name}</p>
            {row.client_contact ? (
              <p className="truncate text-xs text-muted-foreground">{row.client_contact}</p>
            ) : null}
          </div>
        </div>
      ),
    },
    {
      key: "message",
      header: "Latest message",
      className: "max-w-[22rem]",
      cell: (row) => (
        <p className="truncate text-sm text-muted-foreground">
          {row.latest_message_preview ?? "—"}
        </p>
      ),
    },
    {
      key: "intent",
      header: "Intent",
      cell: (row) => <IntentBadge label={row.intent_label} />,
    },
    {
      key: "risk",
      header: "Risk",
      cell: (row) => <RiskBadge level={row.risk_level} />,
    },
    {
      key: "status",
      header: "Status",
      cell: (row) => <StatusBadge status={row.conversation_status} />,
    },
    {
      key: "time",
      header: "Updated",
      headClassName: "text-right",
      className: "text-right whitespace-nowrap text-sm text-muted-foreground",
      cell: (row) => formatRelative(row.latest_message_at ?? row.updated_at),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Inbox"
        description="Every client conversation, classified by intent and risk. High-risk items are highlighted."
        actions={
          data ? (
            <Badge variant="secondary">
              {items.length} {items.length === 1 ? "conversation" : "conversations"}
            </Badge>
          ) : null
        }
      />

      {/* Filters */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="relative flex-1 lg:max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search clients or messages…"
            className="pl-9"
            aria-label="Search inbox"
          />
        </div>
        <div className="grid grid-cols-3 gap-2 sm:flex">
          <FilterSelect
            value={statusFilter}
            onChange={setStatusFilter}
            placeholder="Status"
            allLabel="All statuses"
            options={STATUS_OPTIONS}
          />
          <FilterSelect
            value={riskFilter}
            onChange={setRiskFilter}
            placeholder="Risk"
            allLabel="All risk"
            options={RISK_OPTIONS}
          />
          <FilterSelect
            value={intentFilter}
            onChange={setIntentFilter}
            placeholder="Intent"
            allLabel="All intents"
            options={intentOptions}
          />
        </div>
        {hasActiveFilters ? (
          <Button variant="ghost" size="sm" onClick={clearFilters} className="shrink-0">
            <X /> Clear
          </Button>
        ) : null}
      </div>

      {isLoading ? (
        <LoadingState rows={6} />
      ) : isError ? (
        <ErrorState description="We couldn't load the inbox." onRetry={refetch} />
      ) : (
        <DataTable
          columns={columns}
          rows={items}
          rowKey={(row) => row.conversation_id}
          onRowClick={(row) => navigate(`/inbox/${row.conversation_id}`)}
          rowClassName={(row) =>
            cn(
              row.risk_level?.toLowerCase() === "high" &&
                "bg-destructive/[0.04] hover:bg-destructive/[0.07]",
            )
          }
          emptyState={
            <EmptyState
              icon={InboxIcon}
              title={hasActiveFilters ? "No matching conversations" : "Inbox is clear"}
              description={
                hasActiveFilters
                  ? "Try adjusting or clearing your filters."
                  : "New client messages will show up here automatically."
              }
              action={
                hasActiveFilters ? (
                  <Button variant="outline" size="sm" onClick={clearFilters}>
                    Clear filters
                  </Button>
                ) : undefined
              }
            />
          }
        />
      )}
    </div>
  );
}

function FilterSelect({
  value,
  onChange,
  placeholder,
  allLabel,
  options,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  allLabel: string;
  options: string[];
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-full sm:w-[140px]" aria-label={placeholder}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">{allLabel}</SelectItem>
        {options.map((option) => (
          <SelectItem key={option} value={option}>
            {humanize(option)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
