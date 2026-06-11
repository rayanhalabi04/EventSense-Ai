import { cn } from "@/lib/utils";

/** EventSense AI wordmark + logo. Used in the sidebar and login screen. */
export function BrandMark({
  className,
  tone = "dark",
  withTagline = false,
}: {
  className?: string;
  tone?: "dark" | "light";
  withTagline?: boolean;
}) {
  const isLight = tone === "light";
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <span
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
          isLight ? "bg-primary text-primary-foreground" : "bg-sidebar-accent text-brand-charcoal",
        )}
      >
        <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true" fill="currentColor">
          <path d="M12 3l1.9 4.2L18.5 9l-3.3 3 .9 4.6L12 14.6 7.9 16.6l.9-4.6L5.5 9l4.6-1.8L12 3z" />
        </svg>
      </span>
      <div className="leading-tight">
        <p
          className={cn(
            "font-semibold tracking-tight",
            isLight ? "text-foreground" : "text-sidebar-foreground",
          )}
        >
          EventSense <span className="font-normal opacity-80">AI</span>
        </p>
        {withTagline ? (
          <p className={cn("text-xs", isLight ? "text-muted-foreground" : "text-sidebar-muted")}>
            AI operations assistant for event teams
          </p>
        ) : null}
      </div>
    </div>
  );
}
