"use client";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Icon } from "./icon";

export function Login({ onLogin }: { onLogin: () => void }) {
  const demo = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
  const mutation = useMutation({
    mutationFn: (values: { email: string; password: string }) =>
      api("/auth/login", { method: "POST", body: JSON.stringify(values) }),
    onSuccess: onLogin,
  });
  return (
    <main className="login-page">
      <div className="login-brand">
        <div className="brand-mark">
          <Icon name="layers" size={27} />
        </div>
        stratum<span>RELIABILITY PLATFORM</span>
      </div>
      <div className="login-art" aria-hidden="true">
        <div className="orb orb-one" />
        <div className="orb orb-two" />
        <div className="orbit" />
        <div className="orbit orbit-small" />
        <div className="art-cross">+</div>
      </div>
      <section className="login-copy">
        <span className="eyebrow">
          <span className="live-dot" /> SIGNAL. CONTEXT. CONTROL.
        </span>
        <h1>
          Clarity when
          <br />
          every second
          <br />
          <em>counts.</em>
        </h1>
        <p>
          One place to understand your systems.
          <br />
          From the first signal to the final resolution.
        </p>
        <div className="login-tags">
          <span>
            <Icon name="shield" /> Evidence first
          </span>
          <span>
            <Icon name="pulse" /> Always in context
          </span>
        </div>
      </section>
      <section className="login-card">
        <span className="eyebrow">YOUR OPERATIONS, IN FOCUS</span>
        <h2>Welcome to Stratum</h2>
        <p>Sign in to your reliability workspace.</p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            mutation.mutate({
              email: String(form.get("email")),
              password: String(form.get("password")),
            });
          }}
        >
          <label>
            Email address
            <input
              name="email"
              type="email"
              autoComplete="username"
              placeholder="you@company.com"
              required
              defaultValue={demo ? "demo@stratum.local" : ""}
            />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              minLength={8}
              required
              defaultValue={demo ? "stratum-demo-password" : ""}
            />
          </label>
          {mutation.error && (
            <p className="error-message" role="alert">
              {mutation.error.message}
            </p>
          )}
          <button className="primary wide" disabled={mutation.isPending}>
            {mutation.isPending ? "Connecting…" : "Enter workspace"}
            <Icon name="arrow" />
          </button>
        </form>
        {demo && (
          <div className="demo-callout">
            <Icon name="code" />
            <div>
              <strong>A working demo, ready to explore.</strong>
              <p>
                Preloaded with sample incidents and service data. Changes persist in this workspace.
              </p>
            </div>
          </div>
        )}
        <div className="login-bottom">
          <Icon name="shield" size={14} /> Private sessions · Tenant-scoped access
        </div>
      </section>
      <footer className="login-footer">
        STRATUM / RELIABILITY, IN FOCUS <span>Built for the people behind the uptime.</span>
      </footer>
    </main>
  );
}
