// Turns job markdown into safe HTML.
//
// Job files are written by agents from repository content, so they are untrusted input: a
// prompt-injected spec or review must not be able to run script in the dashboard, which also
// holds archive actions. Everything marked produces is therefore passed through DOMPurify as
// the last step, and raw HTML in the source is escaped rather than interpreted.

import DOMPurify from "dompurify";
import { Marked } from "marked";

// Diagram source travels in this attribute, base64-encoded, and is rendered later by mermaid in
// strict mode; it never reaches the DOM as markup. Encoding is needed because DOMPurify drops an
// attribute whose value contains `-->`, which every flowchart edge does, so raw source would be
// stripped. Base64 also means the source cannot be read as markup at any stage in between.
export const MERMAID_ATTRIBUTE = "data-mermaid";

export function encodeDiagram(source) {
  const bytes = new TextEncoder().encode(source);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

export function decodeDiagram(encoded) {
  const binary = atob(encoded);
  return new TextDecoder().decode(Uint8Array.from(binary, (character) => character.charCodeAt(0)));
}

const markdown = new Marked({
  gfm: true,
  breaks: false,
  renderer: {
    // Source that merely looks like HTML (for example `<script>`) is shown as text.
    html({ text }) {
      return escapeHtml(text);
    },
    code({ text, lang }) {
      if ((lang || "").trim().toLowerCase() === "mermaid") {
        return `<div class="diagram" ${MERMAID_ATTRIBUTE}="${encodeDiagram(text)}"></div>\n`;
      }
      return false;
    },
  },
});

function escapeHtml(text) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Links open in a new tab, so they must not hand the opener to the page they point at.
DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  if (node.tagName === "A" && node.hasAttribute("href")) {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer");
  }
});

export function renderMarkdown(source) {
  const html = markdown.parse(source ?? "", { async: false });
  return DOMPurify.sanitize(html, {
    ADD_ATTR: ["target", MERMAID_ATTRIBUTE],
    // Only the http(s), mailto and in-page schemes; javascript: and data: are dropped.
    ALLOWED_URI_REGEXP: /^(?:https?:|mailto:|#|\/|\.{1,2}\/)/i,
  });
}

const REVIEW_VERDICT = /^VERDICT:\s*(PASS|CHANGES|N\/A)\s*$/;
const ESCALATE = /^(ESCALATE)\b/;

// Mirrors the board: the verdict is the first non-blank line, so a later mention is not one.
export function splitVerdict(text) {
  const lines = (text ?? "").split("\n");
  const index = lines.findIndex((line) => line.trim() !== "");
  if (index === -1) return { verdict: null, label: null, body: text ?? "" };
  const first = lines[index].trim();
  const match = first.match(REVIEW_VERDICT) || first.match(ESCALATE);
  if (!match) return { verdict: null, label: null, body: text };
  return { verdict: match[1], label: first, body: lines.slice(index + 1).join("\n") };
}
