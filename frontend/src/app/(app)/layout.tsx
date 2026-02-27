"use client";

import { AuthProvider, useAuthContext } from "@/lib/auth-context";
import { NavBar } from "@/components/navbar";
import { Spinner } from "@/components/shared";
import type { ReactNode } from "react";

function AppShell({ children }: { children: ReactNode }) {
  const { user, loading, signIn, signOut } = useAuthContext();

  if (loading) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-10">
        <Spinner />
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <NavBar user={user} onSignIn={signIn} onSignOut={signOut} />
      {children}
    </main>
  );
}

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <AppShell>{children}</AppShell>
    </AuthProvider>
  );
}
