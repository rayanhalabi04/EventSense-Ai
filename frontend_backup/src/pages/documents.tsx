import { StatusBadge } from "@/components/badges/status-badge";
import { type Column, DataTable } from "@/components/common/data-table";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "@/components/ui/sonner";
import { useArchiveDocument, useDocuments, useUploadDocument } from "@/hooks/queries";
import { useAuth } from "@/hooks/use-auth";
import { DOCUMENT_TYPE_LABELS, DOCUMENT_TYPE_OPTIONS, formatDate } from "@/lib/format";
import type { DocumentItem, DocumentType } from "@/lib/types";
import { Archive, FileText, Search, Upload } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";

export function DocumentsPage() {
  const { user } = useAuth();
  const canManage = user?.role === "manager" || user?.role === "platform_admin";
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [uploadOpen, setUploadOpen] = useState(false);

  const { data, isLoading, isError, refetch } = useDocuments({
    document_type: typeFilter === "all" ? undefined : typeFilter,
    search: search.trim() || undefined,
    status: "active",
  });
  const archive = useArchiveDocument();

  const documents = data ?? [];

  const columns: Column<DocumentItem>[] = [
    {
      key: "title",
      header: "Document",
      cell: (row) => (
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
            <FileText className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <p className="truncate font-medium text-foreground">{row.title}</p>
            {row.original_filename ? (
              <p className="truncate text-xs text-muted-foreground">{row.original_filename}</p>
            ) : null}
          </div>
        </div>
      ),
    },
    {
      key: "type",
      header: "Type",
      cell: (row) => <Badge variant="secondary">{DOCUMENT_TYPE_LABELS[row.document_type]}</Badge>,
    },
    {
      key: "status",
      header: "Status",
      cell: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: "uploaded",
      header: "Uploaded",
      className: "whitespace-nowrap text-sm text-muted-foreground",
      cell: (row) => formatDate(row.created_at),
    },
    {
      key: "actions",
      header: "",
      headClassName: "text-right",
      className: "text-right",
      cell: (row) =>
        canManage ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              archive.mutate(row.id, {
                onSuccess: () => toast.success("Document archived"),
                onError: (err) =>
                  toast.error(err instanceof Error ? err.message : "Could not archive"),
              });
            }}
          >
            <Archive /> Archive
          </Button>
        ) : null,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Documents"
        description="The tenant knowledge base that grounds AI suggested replies."
        actions={
          canManage ? (
            <Button onClick={() => setUploadOpen(true)}>
              <Upload /> Upload document
            </Button>
          ) : null
        }
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1 sm:max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search documents…"
            className="pl-9"
            aria-label="Search documents"
          />
        </div>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="sm:w-[200px]" aria-label="Filter by type">
            <SelectValue placeholder="Document type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            {DOCUMENT_TYPE_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <LoadingState rows={5} />
      ) : isError ? (
        <ErrorState description="We couldn't load documents." onRetry={refetch} />
      ) : (
        <DataTable
          columns={columns}
          rows={documents}
          rowKey={(row) => row.id}
          emptyState={
            <EmptyState
              icon={FileText}
              title="No documents yet"
              description={
                canManage
                  ? "Upload pricing sheets, FAQs, and policies so the AI can ground its replies."
                  : "Your team hasn't added any documents to the knowledge base yet."
              }
              action={
                canManage ? (
                  <Button onClick={() => setUploadOpen(true)}>
                    <Upload /> Upload document
                  </Button>
                ) : undefined
              }
            />
          }
        />
      )}

      {canManage ? <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} /> : null}
    </div>
  );
}

function UploadDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const upload = useUploadDocument();
  const [docType, setDocType] = useState<DocumentType>("faq");
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const reset = () => {
    setTitle("");
    setFile(null);
    setDocType("faq");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    upload.mutate(
      { file, document_type: docType, title: title.trim() || undefined },
      {
        onSuccess: () => {
          toast.success("Document uploaded");
          onOpenChange(false);
          reset();
        },
        onError: (err) => toast.error(err instanceof Error ? err.message : "Upload failed"),
      },
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) reset();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload document</DialogTitle>
          <DialogDescription>
            Add a .txt file to the knowledge base. Only UTF-8 text files are supported.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="doc-type">Document type</Label>
            <Select value={docType} onValueChange={(v) => setDocType(v as DocumentType)}>
              <SelectTrigger id="doc-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DOCUMENT_TYPE_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="doc-title">Title</Label>
            <Input
              id="doc-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Defaults to the file name"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="doc-file">File (.txt)</Label>
            <Input
              id="doc-file"
              ref={fileInputRef}
              type="file"
              accept=".txt,text/plain"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              required
              className="cursor-pointer file:mr-3 file:cursor-pointer file:rounded file:bg-secondary file:px-2 file:py-1 file:text-secondary-foreground"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={upload.isPending} disabled={!file}>
              <Upload /> Upload
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
