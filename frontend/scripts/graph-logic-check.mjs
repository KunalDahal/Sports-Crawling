import { buildGraph, fitViewport } from "../src/graph-logic.js";

const graph = buildGraph(
  {
    match: "Team A vs Team B",
    status: "running",
    message: "Inspecting root",
    current_url: "https://example.com/root",
    keywords: [{ id: "keyword:1", query: "Team A vs Team B live stream", search_results: 1 }],
    nodes: [
      {
        id: "node:1",
        parent_id: "keyword:1",
        keyword_id: "keyword:1",
        root: true,
        depth: 0,
        url: "https://example.com/root",
        title: "Root page",
        summary: "",
        links: [],
        iframes: [],
        stream_urls: ["https://cdn.example.com/live/master.m3u8"],
        child_ids: ["node:2"],
        classification: "suspicious",
        color: "red",
        reason: "",
        status: "done",
        visited: true,
      },
      {
        id: "node:2",
        parent_id: "node:1",
        keyword_id: "keyword:1",
        root: false,
        depth: 1,
        url: "https://clean.example.org/page",
        title: "Clean page",
        summary: "",
        links: [],
        iframes: [],
        stream_urls: [],
        child_ids: [],
        classification: "clean",
        color: "green",
        reason: "",
        status: "done",
        visited: true,
      },
    ],
    stats: { keywords: 1, roots: 1, visited: 2, official: 0, suspicious: 1, clean: 1 },
  },
  { id: "abc", match: "Team A vs Team B", status: "running" },
);

if (!graph.nodes.length || !graph.edges.length) {
  throw new Error("graph-logic smoke test failed");
}

if (graph.nodes.some((node) => !Array.isArray(node.lines) || node.lines.length === 0)) {
  throw new Error("graph label smoke test failed");
}

const viewport = fitViewport(graph.bounds, { width: 1200, height: 800 });
if (!Number.isFinite(viewport.scale)) {
  throw new Error("fitViewport smoke test failed");
}

console.log("graph logic ok");
