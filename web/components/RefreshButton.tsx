"use client";

import { useRouter } from "next/navigation";

/** Client refresh button — re-fetches the current server-rendered page. */
export default function RefreshButton() {
  const router = useRouter();
  return (
    <button
      type="button"
      onClick={() => router.refresh()}
      className="rounded border border-zinc-700 bg-zinc-800 px-3 py-1 text-sm text-zinc-200 transition hover:bg-zinc-700"
    >
      Refresh
    </button>
  );
}
