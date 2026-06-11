import { StatusBadge } from "@/components/badges/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "@/components/ui/sonner";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useTasks, useUpdateTask } from "@/hooks/queries";
import { formatDate, humanize } from "@/lib/format";
import type { Task, TaskStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ArrowUpRight, CalendarClock, ClipboardList, MoreVertical } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

const TAB_OPTIONS: { value: string; label: string }[] = [
  { value: "all", label: "All" },
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In progress" },
  { value: "completed", label: "Completed" },
];

const NEXT_STATUSES: TaskStatus[] = ["open", "in_progress", "completed", "cancelled"];

function isOverdue(task: Task): boolean {
  if (!task.due_at || task.status === "completed" || task.status === "cancelled") return false;
  return new Date(task.due_at).getTime() < Date.now();
}

export function TasksPage() {
  const [tab, setTab] = useState("all");
  const { data, isLoading, isError, refetch } = useTasks(tab === "all" ? {} : { status: tab });
  const update = useUpdateTask();

  const tasks = data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Tasks"
        description="Follow-up actions created from client conversations."
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
        <LoadingState rows={4} />
      ) : isError ? (
        <ErrorState description="We couldn't load tasks." onRetry={refetch} />
      ) : tasks.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title="No tasks here"
          description="Follow-up tasks you create from a conversation will appear in this list."
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {tasks.map((task) => {
            const overdue = isOverdue(task);
            return (
              <Card key={task.id} className={cn(overdue && "ring-1 ring-destructive/25")}>
                <CardContent className="space-y-3 p-4">
                  <div className="flex items-start justify-between gap-2">
                    <StatusBadge status={task.status} />
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="-mr-1 h-7 w-7">
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuLabel>Set status</DropdownMenuLabel>
                        <DropdownMenuSeparator />
                        {NEXT_STATUSES.filter((s) => s !== task.status).map((status) => (
                          <DropdownMenuItem
                            key={status}
                            onClick={() =>
                              update.mutate(
                                { taskId: task.id, status },
                                {
                                  onSuccess: () => toast.success(`Marked ${humanize(status)}`),
                                  onError: (e) =>
                                    toast.error(
                                      e instanceof Error ? e.message : "Could not update task",
                                    ),
                                },
                              )
                            }
                          >
                            {humanize(status)}
                          </DropdownMenuItem>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>

                  <div>
                    <p className="font-medium leading-snug text-foreground">{task.title}</p>
                    {task.description ? (
                      <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                        {task.description}
                      </p>
                    ) : null}
                  </div>

                  <div className="flex items-center justify-between gap-2 pt-1">
                    <span
                      className={cn(
                        "inline-flex items-center gap-1.5 text-xs",
                        overdue ? "font-medium text-destructive" : "text-muted-foreground",
                      )}
                    >
                      <CalendarClock className="h-3.5 w-3.5" />
                      {task.due_at ? `Due ${formatDate(task.due_at)}` : "No due date"}
                      {overdue ? " · Overdue" : ""}
                    </span>
                    <Button asChild variant="ghost" size="sm" className="h-7 px-2 text-xs">
                      <Link to={`/inbox/${task.conversation_id}`}>
                        Conversation <ArrowUpRight className="h-3.5 w-3.5" />
                      </Link>
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
