"use client";

import LearnTab from "@/app/learn-tab";
import { useAuthContext } from "@/lib/auth-context";

export default function LearnPage() {
  const { token, user } = useAuthContext();
  return <LearnTab token={token} user={user} />;
}
