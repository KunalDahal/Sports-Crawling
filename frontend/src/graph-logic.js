const NODE_SIZE = 96;
const H_GAP = 64;
const V_GAP = 118;
const PAD_X = 100;
const PAD_Y = 96;

export function buildGraph(state, summary) {
  const selectionMap = new Map();
  const nodeMap = new Map();
  const childMap = new Map();
  const roots = ["session"];
  const sessionKey = state?.session_id || summary?.id || "session";

  const rootDetail = {
    kind: "session",
    id: "session",
    match: state?.match || summary?.match || "",
    status: state?.status || summary?.status || "idle",
    message: state?.message || summary?.message || "",
    error: state?.error || summary?.last_error || "",
    currentUrl: state?.current_url || summary?.current_url || "",
    keywords: state?.keywords || [],
    stats: state?.stats || {
      keywords: summary?.keywords || 0,
      roots: summary?.roots || 0,
      visited: summary?.visited || 0,
      official: summary?.official || 0,
      suspicious: summary?.suspicious || 0,
      clean: summary?.clean || 0,
    },
  };

  nodeMap.set("session", {
    id: "session",
    tone: toneFromStatus(rootDetail.status),
    kind: "session",
    label: matchLabel(rootDetail.match || "spcrawler"),
    lines: splitLabel(matchLabel(rootDetail.match || "spcrawler")),
    detail: rootDetail,
  });
  selectionMap.set("session", rootDetail);

  const pageIds = new Set();
  for (const node of state?.nodes || []) {
    pageIds.add(node.id);
  }

  for (const node of state?.nodes || []) {
    const detail = { kind: "page", ...node };
    const parentId = pageIds.has(node.parent_id) ? node.parent_id : "session";
    const label = hostname(node.url);
    nodeMap.set(node.id, {
      id: node.id,
      tone: normalizeTone(node.color, node.classification, node.status),
      kind: "page",
      label,
      lines: splitLabel(label),
      detail,
    });
    addChild(childMap, parentId, node.id);
    selectionMap.set(node.id, detail);
  }

  const positioned = layoutNodes(nodeMap, childMap, roots);
  const nodes = [];
  const edges = [];

  for (const [id, pos] of positioned.positions.entries()) {
    const node = nodeMap.get(id);
    if (!node) continue;
    nodes.push({ ...node, x: pos.x, y: pos.y });
  }

  for (const [parentId, children] of childMap.entries()) {
    const p = positioned.positions.get(parentId);
    if (!p) continue;
    for (const childId of children) {
      const c = positioned.positions.get(childId);
      const child = nodeMap.get(childId);
      if (!c || !child) continue;
      const x1 = p.x + NODE_SIZE / 2;
      const y1 = p.y + NODE_SIZE;
      const x2 = c.x + NODE_SIZE / 2;
      const y2 = c.y;
      const midY = (y1 + y2) / 2;
      edges.push({
        id: `${parentId}-${childId}`,
        tone: child.tone,
        path: `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`,
      });
    }
  }

  return {
    sessionKey,
    rootId: "session",
    nodeSize: NODE_SIZE,
    nodes,
    edges,
    bounds: positioned.bounds,
    selectionMap,
  };
}

export function fitViewport(bounds, size) {
  const paddingX = 48;
  const paddingTop = 24;
  const paddingBottom = 48;
  const scale = clamp(
    Math.min(
      (size.width - paddingX * 2) / bounds.width,
      (size.height - paddingTop - paddingBottom) / bounds.height,
    ),
    0.35,
    1,
  );

  return {
    scale,
    tx: (size.width - bounds.width * scale) / 2 - bounds.minX * scale,
    ty: paddingTop - bounds.minY * scale,
  };
}

function layoutNodes(nodeMap, childMap, roots) {
  const leafColumns = new Map();
  let leafIndex = 0;

  function visibleChildren(id) {
    return (childMap.get(id) || []).filter((childId) => nodeMap.has(childId));
  }

  function assignLeaves(id) {
    const children = visibleChildren(id);
    if (children.length === 0) {
      leafColumns.set(id, leafIndex++);
      return;
    }
    children.forEach(assignLeaves);
  }

  roots.forEach(assignLeaves);

  function xFor(id) {
    const children = visibleChildren(id);
    if (children.length === 0) {
      return PAD_X + (leafColumns.get(id) || 0) * (NODE_SIZE + H_GAP);
    }
    const xs = children.map(xFor);
    return (xs[0] + xs[xs.length - 1]) / 2;
  }

  const positions = new Map();
  const seen = new Set();
  let maxX = PAD_X + NODE_SIZE;
  let maxY = PAD_Y + NODE_SIZE;

  function place(id, depth) {
    if (seen.has(id)) return;
    seen.add(id);
    const x = xFor(id);
    const y = PAD_Y + depth * (NODE_SIZE + V_GAP);
    positions.set(id, { x, y });
    maxX = Math.max(maxX, x + NODE_SIZE);
    maxY = Math.max(maxY, y + NODE_SIZE);
    visibleChildren(id).forEach((childId) => place(childId, depth + 1));
  }

  roots.forEach((id) => place(id, 0));

  return {
    positions,
    bounds: {
      minX: 0,
      minY: 0,
      width: Math.max(960, maxX + PAD_X),
      height: Math.max(560, maxY + PAD_Y),
    },
  };
}

function addChild(childMap, parentId, childId) {
  if (!parentId || parentId === childId) return;
  if (!childMap.has(parentId)) childMap.set(parentId, []);
  const children = childMap.get(parentId);
  if (!children.includes(childId)) children.push(childId);
}

function normalizeTone(color, classification, status) {
  if (color === "blue" || classification === "official") return "blue";
  if (color === "red" || classification === "suspicious") return "red";
  if (color === "green" || classification === "clean") return "green";
  if (status === "error") return "gray";
  return "yellow";
}

function toneFromStatus(status) {
  if (status === "finished") return "green";
  if (status === "failed" || status === "stopped") return "gray";
  return "blue";
}

function hostname(value) {
  if (!value) return "";
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch {
    return value;
  }
}

function matchLabel(value) {
  if (!value) return "match";
  return value.replace(/\s+vs\s+/i, " vs ");
}

function splitLabel(value) {
  const words = value.split(/[.\s/-]+/).filter(Boolean);
  if (words.length <= 1) return [truncate(value, 14)];
  const first = truncate(words.slice(0, Math.ceil(words.length / 2)).join("."), 14);
  const second = truncate(words.slice(Math.ceil(words.length / 2)).join("."), 14);
  return [first, second].filter(Boolean);
}

function truncate(value, size) {
  if (!value) return "";
  return value.length > size ? `${value.slice(0, size - 2)}..` : value;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
