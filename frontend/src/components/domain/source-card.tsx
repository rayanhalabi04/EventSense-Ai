import { Badge } from "@/components/ui/badge";
import { DOCUMENT_TYPE_LABELS } from "@/lib/format";
import type { DocumentType, RagSource } from "@/lib/types";
import { FileText } from "lucide-react";

/** Compact card showing a retrieved RAG source used to ground a suggested reply. */
export function SourceCard({ source }: { source: RagSource }) {
  const typeLabel =
    DOCUMENT_TYPE_LABELS[source.document_type as DocumentType] ?? source.document_type;
  return (
    <div className="rounded-lg border border-border bg-muted/40 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent/50 text-accent-foreground">
            <FileText className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-foreground">{source.document_title}</p>
            <p className="text-xs text-muted-foreground">{typeLabel}</p>
          </div>
        </div>
        {typeof source.score === "number" ? (
          <Badge variant="muted" className="shrink-0">
            {Math.round(source.score * 100)}% match
          </Badge>
        ) : null}
      </div>
      {source.content ? (
        <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-muted-foreground">
          {source.content}
        </p>
      ) : null}
    </div>
  );
}
