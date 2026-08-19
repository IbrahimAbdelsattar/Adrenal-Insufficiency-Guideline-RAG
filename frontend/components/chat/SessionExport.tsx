"use client";

import type { ChatSession } from "@/components/ChatView";

export function exportSessionToMarkdown(sessionToExport: ChatSession): void {
  let exportText = `# Eva AI Clinical Consultation Summary\n`;
  exportText += `**Session Title:** ${sessionToExport.title}\n`;
  exportText += `**Date:** ${new Date(sessionToExport.createdAt).toLocaleString()}\n`;
  exportText += `**Guideline Scope:** NICE NG243 (Adrenal Insufficiency Management)\n\n---\n\n`;

  sessionToExport.messages.forEach((m, idx) => {
    exportText += `### [${m.role === "user" ? "Clinician Query" : "Eva AI Decision Support"}] - ${m.timestamp}\n\n`;
    exportText += `${m.content}\n\n`;
    if (m.citations && m.citations.length > 0) {
      exportText += `#### Evidence Sources:\n`;
      m.citations.forEach((c) => {
        exportText += `- **[Source ${c.source_id}] ${c.document_name}** | Section ${c.section_number} (${c.section_title}) | Page ${c.page_number}\n`;
        if (c.excerpt) {
          exportText += `  > ${c.excerpt}\n`;
        }
      });
      exportText += `\n`;
    }
    if (idx < sessionToExport.messages.length - 1) {
      exportText += `---\n\n`;
    }
  });

  const blob = new Blob([exportText], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `eva-ai-consultation-${sessionToExport.id}.md`;
  link.click();
  URL.revokeObjectURL(url);
}
