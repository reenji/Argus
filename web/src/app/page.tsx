"use client";

import { useCallback, useEffect, useState } from "react";
import { AuthScreen } from "@/components/auth-screen";
import { ArgusConsole } from "@/components/argus-console";
import { Onboarding } from "@/components/onboarding";
import { Button } from "@/components/ui/button";
import { api, ApiError, getToken, onUnauthorized, setToken, type Session, type User } from "@/lib/api";

type View = "loading" | "unreachable" | "auth" | "onboarding" | "console";

export default function Home() {
  const [view, setView] = useState<View>("loading");
  const [user, setUser] = useState<User | null>(null);

  const restoreSession = useCallback(() => {
    if (!getToken()) {
      queueMicrotask(() => setView("auth"));
      return;
    }
    api<User>("/auth/me")
      .then((nextUser) => {
        setUser(nextUser);
        setView(nextUser.gemini_configured ? "console" : "onboarding");
      })
      .catch((reason) => {
        // Only a rejected token ends the session; an outage or deploy keeps it.
        if (reason instanceof ApiError && reason.status === 401) {
          setToken(null);
          setView("auth");
        } else {
          setView("unreachable");
        }
      });
  }, []);

  useEffect(restoreSession, [restoreSession]);

  useEffect(() => onUnauthorized(() => {
    setUser(null);
    setView("auth");
  }), []);

  function handleSession(session: Session) {
    setToken(session.access_token);
    setUser(session.user);
    setView(session.user.gemini_configured ? "console" : "onboarding");
  }

  function signOut() {
    api<void>("/auth/logout", { method: "POST" }).catch(() => undefined);
    setToken(null);
    setUser(null);
    setView("auth");
  }

  if (view === "loading") {
    return <div className="boot-screen"><div className="boot-pulse" aria-label="Initializing ARGUS" /></div>;
  }
  if (view === "unreachable") {
    return (
      <div className="boot-screen" role="alert">
        <p>ARGUS could not reach its server.</p>
        <Button onClick={() => { setView("loading"); restoreSession(); }}>Try again</Button>
      </div>
    );
  }
  if (view === "auth") return <AuthScreen onSession={handleSession} />;
  if (view === "onboarding" && user) {
    return <Onboarding user={user} onComplete={() => setView("console")} onSignOut={signOut} />;
  }
  if (view === "console" && user) return <ArgusConsole user={user} onSignOut={signOut} />;
  return null;
}
