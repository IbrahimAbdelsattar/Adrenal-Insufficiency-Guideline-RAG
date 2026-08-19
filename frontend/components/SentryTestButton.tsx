"use client";

import React, { useState } from "react";
import * as Sentry from "@sentry/nextjs";

export function SentryTestButton() {
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleClientError = () => {
    try {
      throw new Error("Client Test Error: Verifying Sentry frontend exception tracking");
    } catch (error) {
      Sentry.captureException(error);
      setStatus("Frontend test exception captured in Sentry!");
    }
  };

  const handleBackendError = async () => {
    setLoading(true);
    setStatus(null);
    try {
      const res = await fetch("/api/health/sentry-test?trigger_error=true");
      const data = await res.json();
      setStatus(`Backend test response: ${data.status} (Sentry enabled: ${data.sentry_enabled})`);
    } catch (err) {
      setStatus(`Backend test request failed: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <button
        type="button"
        onClick={handleClientError}
        className="px-2.5 py-1 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition"
      >
        Test Frontend Sentry
      </button>
      <button
        type="button"
        onClick={handleBackendError}
        disabled={loading}
        className="px-2.5 py-1 rounded bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition disabled:opacity-50"
      >
        {loading ? "Testing..." : "Test Backend Sentry"}
      </button>
      {status && (
        <span className="text-stone-500 dark:text-stone-400 italic">
          {status}
        </span>
      )}
    </div>
  );
}
