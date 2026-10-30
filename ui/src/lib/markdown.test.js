import { describe, expect, it } from "vitest";
import { decodeDiagram, encodeDiagram, renderMarkdown, splitVerdict } from "./markdown.js";

function parse(html) {
  const container = document.createElement("div");
  container.innerHTML = html;
  return container;
}

describe("renderMarkdown", () => {
  it("renders ordinary markdown", () => {
    const root = parse(renderMarkdown("# Title\n\n- one\n- two\n\n`code`"));
    expect(root.querySelector("h1").textContent).toBe("Title");
    expect(root.querySelectorAll("li")).toHaveLength(2);
    expect(root.querySelector("code").textContent).toBe("code");
  });

  it("renders tables", () => {
    const root = parse(renderMarkdown("| a | b |\n|---|---|\n| 1 | 2 |"));
    expect(root.querySelectorAll("th")).toHaveLength(2);
    expect(root.querySelectorAll("td")).toHaveLength(2);
  });

  describe("hostile job content", () => {
    // Job files are written by agents from repository content, so they are untrusted.
    const hostile = [
      ["script tag", "<script>window.pwned = 1</script>"],
      ["inline handler", '<img src=x onerror="window.pwned = 1">'],
      ["javascript link", "[click](javascript:window.pwned=1)"],
      ["iframe", '<iframe src="https://example.com"></iframe>'],
      ["svg handler", '<svg onload="window.pwned=1"></svg>'],
      ["style injection", "<style>body{display:none}</style>"],
    ];

    for (const [name, source] of hostile) {
      it(`neutralises a ${name}`, () => {
        const html = renderMarkdown(source);
        const root = parse(html);
        expect(root.querySelector("script, iframe, style")).toBeNull();
        // Escaped text may still contain the word "onerror"; what matters is that no element
        // carries a handler attribute or a javascript: URL once the HTML is parsed.
        const live = [...root.querySelectorAll("*")].flatMap((node) =>
          [...node.attributes].filter(({ name, value }) => /^on/i.test(name) || /^\s*javascript:/i.test(value)));
        expect(live).toEqual([]);
        expect(window.pwned).toBeUndefined();
      });
    }

    it("keeps http links but forces them to open safely", () => {
      const link = parse(renderMarkdown("[docs](https://example.com)")).querySelector("a");
      expect(link.getAttribute("href")).toBe("https://example.com");
      expect(link.getAttribute("rel")).toContain("noopener");
      expect(link.getAttribute("target")).toBe("_blank");
    });

    it("does not let a mermaid fence smuggle markup through", () => {
      const html = renderMarkdown('```mermaid\nflowchart LR\n  A["<img src=x onerror=alert(1)>"] --> B\n```');
      expect(html).not.toMatch(/<img/i);
    });
  });

  describe("mermaid fences", () => {
    it("become a placeholder carrying the source, not a code block", () => {
      const root = parse(renderMarkdown("```mermaid\nflowchart LR\n  A --> B\n```"));
      const placeholder = root.querySelector("[data-mermaid]");
      expect(placeholder).not.toBeNull();
      expect(decodeDiagram(placeholder.getAttribute("data-mermaid"))).toBe("flowchart LR\n  A --> B");
      expect(root.querySelector("pre")).toBeNull();
    });

    it("leaves other fenced code as code", () => {
      const root = parse(renderMarkdown("```python\nprint(1)\n```"));
      expect(root.querySelector("pre code").textContent).toContain("print(1)");
      expect(root.querySelector("[data-mermaid]")).toBeNull();
    });

    it("keeps each diagram separate and in order", () => {
      const root = parse(renderMarkdown("```mermaid\ngraph TD\n A-->B\n```\n\ntext\n\n```mermaid\nsequenceDiagram\n A->>B: hi\n```"));
      const sources = [...root.querySelectorAll("[data-mermaid]")].map((node) => decodeDiagram(node.getAttribute("data-mermaid")));
      expect(sources).toEqual(["graph TD\n A-->B", "sequenceDiagram\n A->>B: hi"]);
    });
  });
});

describe("diagram encoding", () => {
  it("round-trips arrows, quotes, markup and non-ASCII text exactly", () => {
    const source = 'flowchart LR\n  A["<b>x</b> & \\"y\\""] --> B\n  B --> C[Zoë ✓]';
    expect(decodeDiagram(encodeDiagram(source))).toBe(source);
  });

  it("survives sanitising for the arrow syntax that DOMPurify would otherwise strip", () => {
    const root = parse(renderMarkdown("```mermaid\nflowchart LR\n  A --> B\n```"));
    expect(root.querySelector("[data-mermaid]")).not.toBeNull();
  });
});

describe("splitVerdict", () => {
  it("extracts a review verdict from the first line", () => {
    expect(splitVerdict("VERDICT: PASS\n\nAll good.")).toEqual({ verdict: "PASS", label: "VERDICT: PASS", body: "\nAll good." });
  });

  it("recognises changes, not applicable and escalate headers", () => {
    expect(splitVerdict("VERDICT: CHANGES\nfix it").verdict).toBe("CHANGES");
    expect(splitVerdict("VERDICT: N/A\nnothing").verdict).toBe("N/A");
    expect(splitVerdict("ESCALATE\n\nReady").verdict).toBe("ESCALATE");
  });

  it("ignores leading blank lines like the board does", () => {
    expect(splitVerdict("\n\nVERDICT: PASS\nok").verdict).toBe("PASS");
  });

  it("returns no verdict for ordinary documents", () => {
    expect(splitVerdict("# Spec\n\nVERDICT: PASS appears later").verdict).toBeNull();
  });
});
