"use client";

import * as Sentry from "@sentry/nextjs";
import NextError from "next/error";
import { useEffect } from "react";

export default function GlobalError({
  error,
}: {
  error: Error & { digest?: string };
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col items-center justify-center bg-stone-900 text-stone-100 p-6">
        <h2 className="text-xl font-bold mb-4">Something went wrong!</h2>
        <p className="text-stone-400 text-sm mb-6 text-center max-w-md">
          A critical application error has been recorded and our team has been notified.
        </p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition"
        >
          Reload Application
        </button>
      </body>
    </html>
  );
}
