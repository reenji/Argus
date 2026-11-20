"use client";

import { FormEvent, useEffect, useState } from "react";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError, type Session } from "@/lib/api";

export function AuthScreen({ onSession }: { onSession: (session: Session) => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  // Set after signup or an unconfirmed sign-in: the address waiting for its link.
  const [pendingEmail, setPendingEmail] = useState("");
  const [notice, setNotice] = useState("");

  // The emailed link opens the app with ?verify=<token>; confirm it and sign in.
  useEffect(() => {
    const url = new URL(window.location.href);
    const token = url.searchParams.get("verify");
    if (!token) return;
    url.searchParams.delete("verify");
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    api<Session>("/auth/verify", { method: "POST", body: JSON.stringify({ token }) })
      .then(onSession)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "This confirmation link is invalid or has expired"));
  }, [onSession]);

  async function resend() {
    setNotice("");
    try {
      await api("/auth/verify/resend", { method: "POST", body: JSON.stringify({ email: pendingEmail }) });
      setNotice(`If ${pendingEmail} is waiting for confirmation, a new link is on its way.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not send a new link");
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    setNotice("");
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") || "");
    try {
      const result = await api<Session | { status: string }>(`/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({
          email: data.get("email"),
          password: data.get("password"),
          ...(mode === "signup" ? { display_name: data.get("display_name") } : {}),
        }),
      });
      if ("access_token" in result) return onSession(result);
      // With email verification on, signup answers the same for every address.
      setPendingEmail(email);
      setNotice(`Check ${email} for a link to confirm your account.`);
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "email_not_verified") setPendingEmail(email);
      setError(reason instanceof Error ? reason.message : "Authentication failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="entry-shell">
      <section className="entry-identity" aria-labelledby="entry-title">
        <div className="wordmark"><span className="wordmark-mark">J</span> ARGUS</div>
        <div className="entry-reactor" aria-hidden="true"><span /></div>
        <p className="eyebrow">Personal intelligence system</p>
        <h1 id="entry-title">Command without friction.</h1>
        <p className="entry-copy">
          Voice, text, research, and creation share one continuous operational context.
        </p>
        <div className="trust-line"><ShieldCheck size={16} /> Your Gemini key is encrypted before storage.</div>
      </section>

      <section className="auth-panel" aria-labelledby="auth-title">
        <div className="mode-switch" role="tablist" aria-label="Account access">
          <button type="button" role="tab" aria-selected={mode === "login"} onClick={() => { setMode("login"); setError(""); }}>Sign in</button>
          <button type="button" role="tab" aria-selected={mode === "signup"} onClick={() => { setMode("signup"); setError(""); }}>Create account</button>
        </div>
        <div>
          <p className="section-index">ACCESS / 01</p>
          <h2 id="auth-title">{mode === "login" ? "Resume session" : "Establish identity"}</h2>
        </div>
        <form onSubmit={submit} className="auth-form">
          {mode === "signup" && (
            <label>Display name<Input name="display_name" autoComplete="name" required placeholder="How ARGUS should address you" /></label>
          )}
          <label>Email<Input name="email" type="email" autoComplete="email" required placeholder="operator@example.com" /></label>
          <label>Password<Input name="password" type="password" minLength={mode === "signup" ? 10 : undefined} maxLength={200} autoComplete={mode === "login" ? "current-password" : "new-password"} required placeholder={mode === "signup" ? "At least 10 characters" : "Your password"} /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          {notice && <p className="form-notice" role="status">{notice}</p>}
          {pendingEmail && (
            <button type="button" className="text-link" onClick={resend}>Send a new confirmation link</button>
          )}
          <Button type="submit" disabled={pending} className="w-full">
            {pending ? "Authorizing" : mode === "login" ? "Enter ARGUS" : "Create secure account"}
            {!pending && <ArrowRight size={16} />}
          </Button>
        </form>
      </section>
    </main>
  );
}
