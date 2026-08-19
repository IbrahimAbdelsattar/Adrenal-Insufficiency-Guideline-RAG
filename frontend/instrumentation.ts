import type { Instrumentation } from "next";

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }

  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}

export const onRequestError: Instrumentation.onRequestError = async (
  err,
  request,
  context
) => {
  if (process.env.NEXT_OUTPUT !== "export") {
    const Sentry = await import("@sentry/nextjs");
    if (Sentry.captureRequestError) {
      return Sentry.captureRequestError(err, request, context);
    }
  }
};
