import { afterEach, describe, expect, it, vi } from "vitest";
import { flushSync, mount, unmount } from "svelte";
import JobCard from "./JobCard.svelte";

const URL = "https://github.com/anaconda/engineering-guard/issues/123";
let component;

function render(job, props = {}) {
  const onopen = vi.fn();
  const target = document.createElement("div");
  document.body.append(target);
  component = mount(JobCard, { target, props: { job, onopen, ...props } });
  flushSync();
  return { target, onopen };
}

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.replaceChildren();
});

const baseJob = { id: "001-x", title: "Do x", stage: "build", repository: "engineering-guard", repo_path: "/work/engineering-guard" };

describe("JobCard issue link", () => {
  it("renders the link beside the card button, not inside it, and opens it safely in a new tab", () => {
    const { target } = render({ ...baseJob, issue_url: URL });
    const link = target.querySelector("a");
    expect(link.getAttribute("href")).toBe(URL);
    expect(link.textContent.trim()).toBe("anaconda/engineering-guard#123");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link.getAttribute("aria-label")).toBe("Open issue anaconda/engineering-guard#123 on GitHub (opens in a new tab)");
    expect(link.getAttribute("title")).toBe("anaconda/engineering-guard#123");
    expect(link.querySelector(".issue-repo").textContent).toBe("anaconda/engineering-guard");
    expect(link.querySelector(".issue-num").textContent).toBe("#123");
    const button = target.querySelector("button.card");
    expect(button.contains(link)).toBe(false);
    expect(button.querySelector("a, button, input")).toBeNull();
  });

  it("does not open the job when the link is clicked, but does when the card is", () => {
    const { target, onopen } = render({ ...baseJob, issue_url: URL });
    const link = target.querySelector("a");
    link.addEventListener("click", (event) => event.preventDefault());
    link.click();
    expect(onopen).not.toHaveBeenCalled();
    target.querySelector("button.card").click();
    expect(onopen).toHaveBeenCalledTimes(1);
  });

  it.each([undefined, "", "javascript:alert(1)", "http://github.com/o/r/issues/1", "https://evil.example/o/r/issues/1", 5])(
    "renders no link for issue_url %j", (issue_url) => {
      const { target } = render({ ...baseJob, issue_url });
      expect(target.querySelector("a")).toBeNull();
      expect(target.querySelector(".card-issue, .card-issue-space")).toBeNull();
    },
  );
});

describe("JobCard repository line", () => {
  it("shows the repository name with the full path as a tooltip", () => {
    const { target } = render(baseJob);
    const line = target.querySelector(".card-path");
    expect(line.textContent).toBe("engineering-guard");
    expect(line.getAttribute("title")).toBe("/work/engineering-guard");
  });

  it("falls back to the path's last segment and omits the line when nothing names the repository", () => {
    expect(render({ id: "1", title: "t", stage: "build", repo_path: "/a/b/named-by-path" }).target.querySelector(".card-path").textContent).toBe("named-by-path");
    unmount(component);
    document.body.replaceChildren();
    expect(render({ id: "1", title: "t", stage: "build" }).target.querySelector(".card-path")).toBeNull();
  });

  it("hides the line when the grouped view asks, since its header already names the repository", () => {
    const { target } = render(baseJob, { showRepository: false });
    expect(target.querySelector(".card-path")).toBeNull();
  });
});
