"use client";

import { FormEvent, ReactNode, useEffect, useState } from "react";
import { LogIn, Mail, ShieldCheck } from "lucide-react";
import type { User } from "firebase/auth";

import {
  isFirebaseAuthConfigured,
  onFirebaseUserChanged,
  signInWithEmail,
  signInWithGoogle,
  signOutFirebase
} from "../lib/firebaseAuth";
import { Button } from "./ui/button";
import { Card, CardContent } from "./ui/card";

export function AuthGate({children}: {children: ReactNode}) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(isFirebaseAuthConfigured);

  useEffect(() => {
    if (!isFirebaseAuthConfigured) {
      return;
    }
    return onFirebaseUserChanged((nextUser) => {
      setUser(nextUser);
      setLoading(false);
    });
  }, []);

  if (!isFirebaseAuthConfigured) {
    return <>{children}</>;
  }

  if (loading) {
    return <AuthShell>Checking access...</AuthShell>;
  }

  if (!user) {
    return <SignInPanel />;
  }

  return (
    <>
      {children}
      <div className="fixed bottom-4 right-4 z-[80] flex max-w-[calc(100vw-2rem)] items-center gap-2 rounded-lg border bg-white px-3 py-2 text-xs shadow-lg">
        <ShieldCheck className="h-4 w-4 text-emerald-700" />
        <span className="truncate text-slate-700">{user.email}</span>
        <Button size="sm" variant="outline" type="button" onClick={() => void signOutFirebase()}>
          Sign out
        </Button>
      </div>
    </>
  );
}

function SignInPanel() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submitEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signInWithEmail(email, password);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign in failed.");
    } finally {
      setBusy(false);
    }
  }

  async function submitGoogle() {
    setBusy(true);
    setError(null);
    try {
      await signInWithGoogle();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell>
      <Card className="w-[min(calc(100vw-2rem),26rem)]">
        <CardContent className="grid gap-4 p-5">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
              <ShieldCheck className="h-4 w-4 text-emerald-700" />
              Authorized operators only
            </div>
          </div>
          <Button type="button" onClick={() => void submitGoogle()} disabled={busy}>
            <LogIn className="mr-2 h-4 w-4" />
            Sign in with Google
          </Button>
          <form className="grid gap-3" onSubmit={submitEmail}>
            <label className="grid gap-1 text-xs font-medium text-slate-700">
              Email
              <input
                className="h-9 rounded-md border px-3 text-sm font-normal"
                autoComplete="email"
                inputMode="email"
                onChange={(event) => setEmail(event.target.value)}
                type="email"
                value={email}
              />
            </label>
            <label className="grid gap-1 text-xs font-medium text-slate-700">
              Password
              <input
                className="h-9 rounded-md border px-3 text-sm font-normal"
                autoComplete="current-password"
                onChange={(event) => setPassword(event.target.value)}
                type="password"
                value={password}
              />
            </label>
            <Button type="submit" variant="secondary" disabled={busy || !email || !password}>
              <Mail className="mr-2 h-4 w-4" />
              Sign in with email
            </Button>
          </form>
          {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900">{error}</div> : null}
        </CardContent>
      </Card>
    </AuthShell>
  );
}

function AuthShell({children}: {children: ReactNode}) {
  return <main className="grid min-h-screen place-items-center bg-background p-4">{children}</main>;
}
