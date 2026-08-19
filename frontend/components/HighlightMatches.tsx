import { Children, cloneElement, isValidElement } from "react";
import type { ReactElement, ReactNode } from "react";

const WORD_PATTERN = /[\p{L}\p{N}]+/gu;

function normalizeWord(word: string): string {
  return word.normalize("NFKD").replace(/\p{M}/gu, "").toLocaleLowerCase();
}

function getQueryTerms(query: string): Set<string> {
  return new Set(
    Array.from(query.matchAll(WORD_PATTERN), ([word]) => normalizeWord(word)).filter(
      (word) => word.length > 1,
    ),
  );
}

function highlightText(text: string, terms: Set<string>): ReactNode {
  const matches = Array.from(text.matchAll(WORD_PATTERN));

  if (!matches.some(([word]) => terms.has(normalizeWord(word)))) {
    return text;
  }

  const parts: ReactNode[] = [];
  let cursor = 0;

  matches.forEach((match) => {
    const word = match[0];
    const index = match.index;

    if (index > cursor) {
      parts.push(text.slice(cursor, index));
    }

    if (terms.has(normalizeWord(word))) {
      parts.push(
        <mark
          className="rounded-sm bg-accent-bright/20 px-0.5 font-semibold text-ink ring-1 ring-accent-bright/30"
          key={`${index}-${word}`}
        >
          {word}
        </mark>,
      );
    } else {
      parts.push(word);
    }

    cursor = index + word.length;
  });

  if (cursor < text.length) {
    parts.push(text.slice(cursor));
  }

  return parts;
}

function highlightNode(node: ReactNode, terms: Set<string>): ReactNode {
  if (typeof node === "string") {
    return highlightText(node, terms);
  }

  if (isValidElement<{ children?: ReactNode }>(node) && node.props.children !== undefined) {
    return cloneElement(
      node as ReactElement<{ children?: ReactNode }>,
      undefined,
      highlightNodes(node.props.children, terms),
    );
  }

  return node;
}

function highlightNodes(children: ReactNode, terms: Set<string>): ReactNode {
  return Children.map(children, (child) => highlightNode(child, terms));
}

interface HighlightMatchesProps {
  children: ReactNode;
  query: string;
}

export function HighlightMatches({ children, query }: HighlightMatchesProps) {
  const terms = getQueryTerms(query);

  if (terms.size === 0) {
    return children;
  }

  return highlightNodes(children, terms);
}
