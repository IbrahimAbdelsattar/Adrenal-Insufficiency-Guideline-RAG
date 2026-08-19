import { Children, cloneElement, isValidElement } from "react";
import type { ReactElement, ReactNode } from "react";

/**
 * Turns "[Source N]" (and "[Source N, 1.7.1]") occurrences in rendered
 * markdown text into clickable buttons that jump to and flash-highlight the
 * matching evidence card. Walks the same way HighlightMatches.tsx does, so
 * the two can be nested around each other without either one losing track
 * of the other's output.
 */
const SOURCE_MARKER_PATTERN = /\[Source\s*(\d+)(?:[^\]]*)\]/gi;

function linkifyText(text: string, onCite: (sourceId: string) => void): ReactNode {
  if (!SOURCE_MARKER_PATTERN.test(text)) {
    return text;
  }
  SOURCE_MARKER_PATTERN.lastIndex = 0;

  const parts: ReactNode[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = SOURCE_MARKER_PATTERN.exec(text)) !== null) {
    const [full, sourceId] = match;
    const index = match.index;

    if (index > cursor) {
      parts.push(text.slice(cursor, index));
    }

    parts.push(
      <button
        key={`${index}-${sourceId}`}
        type="button"
        onClick={() => onCite(sourceId)}
        className="citation-marker mono-pill mx-0.5 cursor-pointer px-1.5 py-0 align-baseline font-mono text-[0.85em] font-extrabold text-accent-bright transition-transform hover:scale-105"
        title={`Jump to Source ${sourceId}`}
      >
        {full}
      </button>,
    );

    cursor = index + full.length;
  }

  if (cursor < text.length) {
    parts.push(text.slice(cursor));
  }

  return parts;
}

function isCitationButton(node: ReactNode): boolean {
  if (!isValidElement<{ className?: string }>(node)) return false;
  return typeof node.props.className === "string" && node.props.className.includes("citation-marker");
}

function linkifyNode(node: ReactNode, onCite: (sourceId: string) => void): ReactNode {
  if (typeof node === "string") {
    return linkifyText(node, onCite);
  }

  // A nested <li><ul><li>...</li></ul></li> markdown list has react-markdown
  // invoke the `li` renderer for the inner item first, then again for the
  // outer one with the inner item's *already-rendered* output as children.
  // Without this guard, the outer CitationMarkers pass re-scans the inner
  // pass's output, finds the marker text still inside the button's own
  // children prop, and wraps a second <button> around it -- invalid nested
  // buttons and a hydration mismatch. Once a node is a citation button,
  // leave it exactly as produced; never recurse into it again.
  if (isCitationButton(node)) {
    return node;
  }

  if (isValidElement<{ children?: ReactNode }>(node) && node.props.children !== undefined) {
    return cloneElement(
      node as ReactElement<{ children?: ReactNode }>,
      undefined,
      linkifyNodes(node.props.children, onCite),
    );
  }

  return node;
}

function linkifyNodes(children: ReactNode, onCite: (sourceId: string) => void): ReactNode {
  return Children.map(children, (child) => linkifyNode(child, onCite));
}

interface CitationMarkersProps {
  children: ReactNode;
  onCite: (sourceId: string) => void;
}

export function CitationMarkers({ children, onCite }: CitationMarkersProps) {
  return linkifyNodes(children, onCite);
}
