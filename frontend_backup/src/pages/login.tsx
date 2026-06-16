import { BrandMark } from "@/components/layout/brand-mark";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/hooks/use-auth";
import { ApiError } from "@/lib/api";
import { ArrowRight, ShieldCheck, Sparkles } from "lucide-react";
import { type FormEvent, useState } from "react";

const HIGHLIGHTS = [
  "Classify intent and flag risk on every client message",
  "Ground suggested replies in your own tenant documents",
  "Keep humans in control — nothing is sent automatically",
];

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Incorrect email or password. Please try again.");
      } else if (err instanceof Error) {
        setError(err.message || "Unable to sign in. Please try again.");
      } else {
        setError("Unable to sign in. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      {/* Brand panel */}
      <div className="relative hidden flex-col justify-between overflow-hidden bg-sidebar p-12 text-sidebar-foreground lg:flex">
        <div
          className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-sidebar-accent/20 blur-3xl"
          aria-hidden="true"
        />
        <div
          className="pointer-events-none absolute -bottom-32 -left-16 h-80 w-80 rounded-full bg-brand-rose/10 blur-3xl"
          aria-hidden="true"
        />
        <BrandMark tone="dark" />
        <div className="relative max-w-md">
          <h2 className="text-3xl font-semibold leading-tight tracking-tight text-balance">
            The calm command center for your client conversations.
          </h2>
          <p className="mt-3 text-sidebar-muted">
            EventSense AI helps wedding planners and event teams stay on top of every message — with
            AI that assists, never replaces, your judgment.
          </p>
          <ul className="mt-8 space-y-3">
            {HIGHLIGHTS.map((item) => (
              <li key={item} className="flex items-start gap-3 text-sm text-sidebar-foreground/90">
                <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-sidebar-accent" />
                {item}
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-sidebar-muted">
          © {new Date().getFullYear()} EventSense AI · AI operations assistant for event teams
        </p>
      </div>

      {/* Form panel */}
      <div className="flex items-center justify-center bg-background px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden">
            <BrandMark tone="light" withTagline />
          </div>
          <div className="mb-7">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-3 py-1 text-xs font-medium text-secondary-foreground">
              <Sparkles className="h-3.5 w-3.5" /> Welcome back
            </span>
            <h1 className="mt-4 text-2xl font-semibold tracking-tight text-foreground">
              Sign in to your workspace
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Enter your team credentials to continue.
            </p>
          </div>

          <Card className="p-6">
            <form onSubmit={onSubmit} className="space-y-4" noValidate>
              <div className="space-y-1.5">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@agency.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>

              {error ? (
                <p
                  role="alert"
                  className="rounded-md border border-destructive/25 bg-destructive/8 px-3 py-2 text-sm text-destructive"
                >
                  {error}
                </p>
              ) : null}

              <Button type="submit" className="w-full" loading={submitting}>
                Sign in
                {!submitting ? <ArrowRight /> : null}
              </Button>
            </form>
          </Card>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            Demo access: <span className="font-medium">admin@elegant-weddings.demo</span> ·{" "}
            <span className="font-medium">demo-password-1</span>
          </p>
        </div>
      </div>
    </div>
  );
}
