import { IntentBadge } from "@/components/badges/intent-badge";
import { RiskBadge } from "@/components/badges/risk-badge";
import { DemoMetricCard } from "@/components/domain/demo-metric-card";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/sonner";
import { Textarea } from "@/components/ui/textarea";
import { useSimulateMessage } from "@/hooks/queries";
import { formatConfidence, humanize } from "@/lib/format";
import type { SimulatorMessageResponse } from "@/lib/types";
import {
  BrainCircuit,
  Building2,
  FileSearch,
  type LucideIcon,
  Send,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { type FormEvent, useState } from "react";

/**
 * Evaluation suite descriptors. Counts reflect the evaluation artifacts that
 * live in the repository (evals/). They describe what the system is tested on;
 * the live demo below exercises the real classifier in real time.
 */
const SUITES: {
  title: string;
  icon: LucideIcon;
  metric: string;
  caption: string;
  status: "pass" | "warn" | "info";
}[] = [
  {
    title: "Intent classifier",
    icon: BrainCircuit,
    metric: "Loaded",
    caption: "TF-IDF + logistic regression baseline, served live via the API.",
    status: "pass",
  },
  {
    title: "RAG retrieval",
    icon: FileSearch,
    metric: "10 cases",
    caption: "Golden-set Q&A grounded in tenant documents (pgvector retrieval).",
    status: "info",
  },
  {
    title: "Guardrails",
    icon: ShieldCheck,
    metric: "20 prompts",
    caption: "Red-team prompt suite covering unsafe and out-of-scope requests.",
    status: "pass",
  },
  {
    title: "Tenant isolation",
    icon: Building2,
    metric: "Enforced",
    caption: "Every query is scoped to the authenticated tenant — no cross-tenant access.",
    status: "pass",
  },
];

const SAMPLE_PROMPTS = [
  "Hi! What are your pricing packages for a 150-guest wedding in June?",
  "We need to cancel and want a full refund immediately or we'll dispute the charge.",
  "Can you confirm the deposit is refundable if we reschedule to next year?",
];

export function EvaluationPage() {
  const simulate = useSimulateMessage();
  const [clientName, setClientName] = useState("Demo Client");
  const [body, setBody] = useState(SAMPLE_PROMPTS[0]);
  const [result, setResult] = useState<SimulatorMessageResponse | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    simulate.mutate(
      { client_name: clientName.trim() || "Demo Client", body: body.trim() },
      {
        onSuccess: (data) => {
          setResult(data);
          toast.success("Message classified");
        },
        onError: (err) => toast.error(err instanceof Error ? err.message : "Classification failed"),
      },
    );
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Evaluation & demo"
        description="See EventSense AI working in real time, and how the system is evaluated for quality and safety."
      />

      {/* Evaluation suites */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {SUITES.map((suite) => (
          <DemoMetricCard
            key={suite.title}
            title={suite.title}
            icon={suite.icon}
            metric={suite.metric}
            caption={suite.caption}
            status={suite.status}
          />
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        {/* Live classifier demo */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <Sparkles className="h-4 w-4" />
              </span>
              Live AI demo
            </CardTitle>
            <CardDescription>
              Send a sample client message and watch the AI classify intent and assess risk
              instantly. This creates a real conversation in the inbox.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="demo-name">Client name</Label>
                <Input
                  id="demo-name"
                  value={clientName}
                  onChange={(e) => setClientName(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="demo-body">Message</Label>
                <Textarea
                  id="demo-body"
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  rows={4}
                  required
                />
              </div>
              <div className="flex flex-wrap gap-1.5">
                {SAMPLE_PROMPTS.map((prompt, i) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => setBody(prompt)}
                    className="rounded-full border border-border bg-muted/50 px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-secondary-foreground"
                  >
                    Sample {i + 1}
                  </button>
                ))}
              </div>
              <Button type="submit" loading={simulate.isPending} disabled={!body.trim()}>
                <Send /> Classify message
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Result panel */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Classification result</CardTitle>
            <CardDescription>What the AI detected for the latest message.</CardDescription>
          </CardHeader>
          <CardContent>
            {!result ? (
              <div className="flex h-full min-h-[16rem] flex-col items-center justify-center rounded-lg border border-dashed border-border text-center">
                <BrainCircuit className="h-8 w-8 text-muted-foreground/60" />
                <p className="mt-3 text-sm text-muted-foreground">
                  Send a message to see live intent and risk results.
                </p>
              </div>
            ) : (
              <dl className="space-y-4">
                <ResultRow label="Detected intent">
                  <div className="flex items-center gap-2">
                    <IntentBadge label={result.intent_label} />
                    <span className="text-sm text-muted-foreground">
                      {formatConfidence(result.intent_confidence)} confidence
                    </span>
                  </div>
                </ResultRow>
                <ResultRow label="Risk level">
                  <RiskBadge level={result.risk_level} />
                </ResultRow>
                {result.risk_reason ? (
                  <ResultRow label="Risk reason">
                    <p className="text-sm text-foreground">{result.risk_reason}</p>
                  </ResultRow>
                ) : null}
                {result.risk_flags?.length ? (
                  <ResultRow label="Flags">
                    <div className="flex flex-wrap gap-1.5">
                      {result.risk_flags.map((flag) => (
                        <Badge key={flag} variant="outline">
                          {humanize(flag)}
                        </Badge>
                      ))}
                    </div>
                  </ResultRow>
                ) : null}
                <ResultRow label="Conversation">
                  <Badge variant="secondary">
                    {result.is_new_conversation
                      ? "New conversation created"
                      : "Existing conversation"}
                  </Badge>
                </ResultRow>
              </dl>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function ResultRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7rem_1fr] items-start gap-3 border-b border-border pb-3 last:border-0 last:pb-0">
      <dt className="text-sm font-medium text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}
