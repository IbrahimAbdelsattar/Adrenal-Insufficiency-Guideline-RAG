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

function linkifyNode(node: ReactNode, onCite: (sourceId: string) => void): ReactNode {
  if (typeof node === "string") {
    return linkifyText(node, onCite);
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
