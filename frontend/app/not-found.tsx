import Link from "next/link";

/**
 * Required explicitly: `output: "export"` cannot synthesise the default
 * not-found page and fails the build without it.
 */
export default function NotFound() {
  return (
    <div className="mx-auto max-w-md py-20 text-center">
      <p className="font-mono text-5xl font-bold text-ink-faint">404</p>
      <h1 className="mt-4 text-lg font-bold text-ink">Page not found</h1>
      <p className="mt-2 text-sm text-ink-dim">
        That route does not exist in the evidence inspector.
      </p>
      <Link
        href="/"
        className="mt-6 inline-block rounded-xl border border-line px-5 py-2.5 text-sm font-semibold text-accent-bright hover:border-accent-bright/50"
      >
        Back to search
      </Link>
    </div>
  );
}
