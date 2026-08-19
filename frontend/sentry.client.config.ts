// This file configures the initialization of Sentry on the client browser.
// The config you add here will be used whenever a users loads a page in their browser.
// https://docs.sentry.io/platforms/javascript/guides/nextjs/

import * as Sentry from "@sentry/nextjs";

const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN || "";

if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,

    // Adjust this value in production, or use tracesSampler for greater control
    tracesSampleRate: process.env.NODE_ENV === "production" ? 0.1 : 1.0,

    // Setting this option to true will print useful information to the console while you're setting up Sentry.
    debug: false,

    // Do not transmit raw IP addresses or PII by default for HIPAA/clinical safety
    sendDefaultPii: false,

    replaysOnErrorSampleRate: 1.0,
    replaysSessionSampleRate: 0.0,

    // Client-side PHI / PII & Secret Sanitization
    beforeSend(event) {
      if (event.request?.headers) {
        delete (event.request.headers as Record<string, string>)["authorization"];
        delete (event.request.headers as Record<string, string>)["cookie"];
      }

      // Sanitize URL query parameters that may contain sensitive terms
      if (event.request?.url) {
        event.request.url = event.request.url.replace(
          /([?&](?:query|q|token|key|secret)=)[^&]+/gi,
          "$1[REDACTED]"
        );
      }

      // Mask potential emails or phone numbers in messages
      if (event.message) {
        event.message = event.message
          .replace(/[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+/g, "[REDACTED_EMAIL]")
          .replace(/(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}/g, "[REDACTED_PHONE]");
      }

      return event;
    },
  });
}
