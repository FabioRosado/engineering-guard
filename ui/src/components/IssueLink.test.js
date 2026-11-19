import { afterEach, describe, expect, it } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import IssueLink from "./IssueLink.svelte";

// JobViewer pulls in the theme store, which reads matchMedia when it is first imported; jsdom has none.
window.matchMedia ??= () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
const { default: JobViewer } = await import("./JobViewer.svelte");

const URL = "https://github.com/anaconda/engineering-guard/issues/123";
let component;

function render(Component, props) {
  const target = document.createElement("div");
  document.body.append(target);
  component = mount(Component, { target, props });
  flushSync();
  return target;
}

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.replaceChildren();
});

describe("IssueLink", () => {
  it("renders a safe external link with the repository and number in separate parts", () => {
    const link = render(IssueLink, { job: { issue_url: URL } }).querySelector("a");
    expect(link.getAttribute("href")).toBe(URL);
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link.getAttribute("title")).toBe("anaconda/engineering-guard#123");
    expect(link.getAttribute("aria-label")).toBe("Open issue anaconda/engineering-guard#123 on GitHub (opens in a new tab)");
    expect(link.querySelector(".issue-repo").textContent).toBe("anaconda/engineering-guard");
    expect(link.querySelector(".issue-num").textContent).toBe("#123");
  });

  it.each([{}, { issue_url: "javascript:alert(1)" }, { issue_url: "http://github.com/o/r/issues/1" }, { issue_url: 7 }])(
    "renders nothing for %j", (job) => {
      expect(render(IssueLink, { job }).innerHTML.trim()).not.toContain("<a");
    },
  );
});

describe("JobViewer header", () => {
  const job = { id: "001-x", title: "Do x", repo_path: "/work/r", stage: "build", files: {} };

  it("shows the issue link next to the title when the job has one", () => {
    const target = render(JobViewer, { job: { ...job, issue_url: URL }, canArchive: false });
    const link = target.querySelector(".modal-heading a.issue-link");
    expect(link.getAttribute("href")).toBe(URL);
    expect(target.querySelector(".modal-title").textContent).toContain("Do x");
  });

  it("shows no link when the job has no issue", () => {
    const target = render(JobViewer, { job, canArchive: false });
    expect(target.querySelector(".modal-heading a")).toBeNull();
    expect(target.querySelector(".modal-title").textContent).toContain("Do x");
  });
});
