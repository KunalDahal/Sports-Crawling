import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { buildGraph, fitViewport } from "./graph-logic.js";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8080";

const emptyForm = {
  match: "",
  api_key: "",
  proxy_url: "",
};

function App() {
  const [form, setForm] = useState(emptyForm);
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState("");
  const [state, setState] = useState(null);
  const [selectedId, setSelectedId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    refreshSessions();
    const timer = setInterval(refreshSessions, 3000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!activeId) {
      setState(null);
      setSelectedId("");
      return undefined;
    }

    let closed = false;
    setSelectedId("");

    fetch(`${API_BASE}/api/sessions/${activeId}/state`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!closed && data) {
          setState(data);
          setError("");
        }
      })
      .catch(() => {});

    const source = new EventSource(`${API_BASE}/api/sessions/${activeId}/stream`);
    source.addEventListener("state", (message) => {
      if (closed) return;
      setState(JSON.parse(message.data));
      setError("");
    });
    source.onerror = () => {};

    return () => {
      closed = true;
      source.close();
    };
  }, [activeId]);

  async function refreshSessions() {
    try {
      const res = await fetch(`${API_BASE}/api/sessions`);
      if (!res.ok) return [];
      const data = await res.json();
      setSessions(data);
      setActiveId((current) => {
        if (!current) return data[0]?.id || "";
        if (data.some((session) => session.id === current)) return current;
        return data[0]?.id || "";
      });
      return data;
    } catch {
      return [];
    }
  }

  async function startSession(e) {
    e.preventDefault();
    setBusy(true);
    setError("");

    try {
      const res = await fetch(`${API_BASE}/api/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not start crawl");
      setActiveId(data.id);
      setSelectedId("");
      setForm((current) => ({ ...current, match: "" }));
      await refreshSessions();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function stopSession(id) {
    await fetch(`${API_BASE}/api/sessions/${id}`, { method: "DELETE" });
    await refreshSessions();
  }

  async function removeSession(id) {
    const confirmed = window.confirm("Remove this session?");
    if (!confirmed) return;

    const res = await fetch(`${API_BASE}/api/sessions/${id}/remove`, { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setError(data.error || "Could not remove session");
      return;
    }

    const next = await refreshSessions();
    if (activeId === id) {
      setActiveId(next[0]?.id || "");
      setState(null);
      setSelectedId("");
    }
  }

  const active = sessions.find((session) => session.id === activeId) || null;
  const graph = useMemo(() => buildGraph(state, active), [state, active]);
  const selected = selectedId ? graph.selectionMap.get(selectedId) || null : null;
  const currentNode = useMemo(() => {
    if (!state?.current_node_id || !Array.isArray(state?.nodes)) return null;
    return state.nodes.find((node) => node.id === state.current_node_id) || null;
  }, [state]);
  const liveDepth = Number.isInteger(currentNode?.depth) ? currentNode.depth : "-";
  const liveUrl = state?.current_url || currentNode?.url || "-";
  const liveStatus = currentNode && !currentNode.visited
    ? state?.message || currentNode?.reason || "-"
    : currentNode?.reason || state?.message || "-";
  const liveNodeLabel = currentNode?.id || "-";
  const liveError = error || state?.error || (currentNode?.status === "error" ? currentNode?.reason : "") || "-";

  useEffect(() => {
    if (selectedId && !graph.selectionMap.has(selectedId)) {
      setSelectedId("");
    }
  }, [graph.selectionMap, selectedId]);

  return (
    <main className="shell">
      <section className="workspace">
        <header className="toolbar">
          <div className="toolbar-title">
            <p className="eyebrow">spcrawler</p>
            <h1>DFS graph</h1>
          </div>

          <form className="toolbar-form" onSubmit={startSession}>
            <input
              value={form.match}
              onChange={(e) => setForm({ ...form, match: e.target.value })}
              placeholder="Team A vs Team B"
              required
            />
            <input
              type="password"
              value={form.api_key}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              placeholder="Gemini API key"
            />
            <input
              value={form.proxy_url}
              onChange={(e) => setForm({ ...form, proxy_url: e.target.value })}
              placeholder="Proxy"
            />
            <button disabled={busy}>{busy ? "Starting" : "Start"}</button>
          </form>

          <div className="toolbar-side">
            <select value={activeId} onChange={(e) => setActiveId(e.target.value)}>
              <option value="">{sessions.length ? "Choose session" : "No sessions"}</option>
              {sessions.map((session) => (
                <option key={session.id} value={session.id}>
                  {session.match || "Session"} | {session.status}
                </option>
              ))}
            </select>

            {active && (
              <div className="toolbar-actions">
                {["running", "starting", "stopping"].includes(active.status) && (
                  <button className="ghost" onClick={() => stopSession(active.id)} type="button">
                    Stop
                  </button>
                )}
                <button className="danger" onClick={() => removeSession(active.id)} type="button">
                  Remove
                </button>
              </div>
            )}
          </div>
        </header>

        <div className="summary-row">
          <Metric label="Status" value={active?.status || state?.status || "waiting"} tone={toneFromStatus(active?.status || state?.status || "idle")} />
          <Metric label="Keywords" value={state?.stats?.keywords ?? active?.keywords ?? 0} />
          <Metric label="Roots" value={state?.stats?.roots ?? active?.roots ?? 0} />
          <Metric label="Visited" value={state?.stats?.visited ?? active?.visited ?? 0} />
          <Metric label="Official" value={state?.stats?.official ?? active?.official ?? 0} tone="blue" />
          <Metric label="Suspicious" value={state?.stats?.suspicious ?? active?.suspicious ?? 0} tone="red" />
          <Metric label="Clean" value={state?.stats?.clean ?? active?.clean ?? 0} tone="green" />
        </div>

        <section className="activity-bar">
          <div className="activity-section">
            <div className="activity-head">
              <p className="eyebrow">Live activity</p>
              <strong>{state?.message || "Waiting"}</strong>
            </div>
            <div className="activity-grid">
              <div className="activity-item">
                <span>Current node</span>
                <strong>{liveNodeLabel}</strong>
              </div>
              <div className="activity-item">
                <span>Current depth</span>
                <strong>{liveDepth}</strong>
              </div>
              <div className="activity-item activity-item-wide">
                <span>Current url</span>
                <strong>{liveUrl}</strong>
              </div>
              <div className="activity-item activity-item-wide">
                <span>Status</span>
                <strong>{liveStatus}</strong>
              </div>
            </div>
          </div>

          <div className="activity-section activity-error-panel">
            <div className="activity-head">
              <p className="eyebrow">Error</p>
              <strong>{liveError === "-" ? "None" : "Active"}</strong>
            </div>
            <div className="activity-grid activity-grid-error">
              <div className="activity-item activity-item-wide">
                <span>Current error</span>
                <strong>{liveError}</strong>
              </div>
            </div>
          </div>
        </section>

        <TreeCanvas
          graph={graph}
          selectedId={selectedId}
          selected={selected}
          onSelect={setSelectedId}
          onClose={() => setSelectedId("")}
        />
      </section>
    </main>
  );
}

function Metric({ label, value, tone = "gray" }) {
  return (
    <div className={`metric metric-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TreeCanvas({ graph, selectedId, selected, onSelect, onClose }) {
  const containerRef = useRef(null);
  const dragRef = useRef(null);
  const fittedSessionRef = useRef("");
  const hasAutoFitRef = useRef(false);
  const userMovedRef = useRef(false);
  const [size, setSize] = useState({ width: 960, height: 640 });
  const [viewport, setViewport] = useState({ scale: 1, tx: 40, ty: 40 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return undefined;

    const updateSize = () => {
      setSize({
        width: Math.max(320, el.clientWidth),
        height: Math.max(460, el.clientHeight),
      });
    };

    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const sessionChanged = fittedSessionRef.current !== graph.sessionKey;
    if (sessionChanged) {
      fittedSessionRef.current = graph.sessionKey;
      hasAutoFitRef.current = false;
      userMovedRef.current = false;
    }

    if (!graph.nodes.length || size.width <= 0 || size.height <= 0) {
      return;
    }

    if (hasAutoFitRef.current || userMovedRef.current) {
      return;
    }

    setViewport(fitViewport(graph.bounds, size));
    hasAutoFitRef.current = true;
  }, [graph.sessionKey, graph.nodes.length, graph.bounds, size.width, size.height]);

  useEffect(() => {
    const move = (e) => {
      if (!dragRef.current) return;
      const { startX, startY, originTx, originTy } = dragRef.current;
      setViewport((current) => ({
        ...current,
        tx: originTx + (e.clientX - startX),
        ty: originTy + (e.clientY - startY),
      }));
    };

    const up = () => {
      dragRef.current = null;
    };

    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, []);

  function zoomBy(factor) {
    userMovedRef.current = true;
    setViewport((current) => {
      const centerX = size.width / 2;
      const centerY = size.height / 2;
      const nextScale = clamp(current.scale * factor, 0.35, 2.2);
      const graphX = (centerX - current.tx) / current.scale;
      const graphY = (centerY - current.ty) / current.scale;
      return {
        scale: nextScale,
        tx: centerX - graphX * nextScale,
        ty: centerY - graphY * nextScale,
      };
    });
  }

  function startDrag(e) {
    if (e.target.closest("[data-node='true']")) return;
    userMovedRef.current = true;
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      originTx: viewport.tx,
      originTy: viewport.ty,
    };
  }

  return (
    <section className="graph-panel">
      <div className="graph-head">
        <div>
          <h2>Domain graph</h2>
          <p>Blue official, red suspicious, green clean</p>
        </div>
        <div className="graph-actions">
          <button className="mini-btn" type="button" onClick={() => zoomBy(1.14)}>
            +
          </button>
          <button className="mini-btn" type="button" onClick={() => zoomBy(0.88)}>
            -
          </button>
          <button
            className="mini-btn"
            type="button"
            onClick={() => {
              userMovedRef.current = false;
              hasAutoFitRef.current = true;
              setViewport(fitViewport(graph.bounds, size));
            }}
          >
            Fit
          </button>
        </div>
      </div>

      <div className="graph-canvas" ref={containerRef} onPointerDown={startDrag} onClick={onClose}>
        {graph.nodes.length === 0 ? (
          <div className="empty-state">Start a crawl to populate the graph.</div>
        ) : (
          <>
            <svg className="tree-svg" width={size.width} height={size.height} viewBox={`0 0 ${size.width} ${size.height}`}>
              <rect className="canvas-hit" x="0" y="0" width={size.width} height={size.height} />
              <g transform={`translate(${viewport.tx} ${viewport.ty}) scale(${viewport.scale})`}>
                {graph.edges.map((edge) => (
                  <path key={edge.id} className={`tree-edge edge-${edge.tone}`} d={edge.path} />
                ))}
                {graph.nodes.map((node) => (
                  <g
                    key={node.id}
                    className="tree-node-group"
                    data-node="true"
                    transform={`translate(${node.x} ${node.y})`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelect(node.id);
                    }}
                  >
                    <circle
                      className={`tree-node-circle tone-${node.tone}${selectedId === node.id ? " selected" : ""}`}
                      cx={graph.nodeSize / 2}
                      cy={graph.nodeSize / 2}
                      r={graph.nodeSize / 2 - 4}
                    />
                    <text className="tree-node-label" x={graph.nodeSize / 2} y={selectedId === node.id ? 38 : 42}>
                      {node.lines.map((line, index) => (
                        <tspan key={`${node.id}-${index}`} x={graph.nodeSize / 2} dy={index === 0 ? 0 : 15}>
                          {line}
                        </tspan>
                      ))}
                    </text>
                  </g>
                ))}
              </g>
            </svg>

            {selected && (
              <div className="popup-layer" onClick={(e) => e.stopPropagation()}>
                <NodePopup detail={selected} onClose={onClose} />
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

function NodePopup({ detail, onClose }) {
  return (
    <div className="node-popup">
      <div className="popup-head">
        <div>
          <p className="eyebrow">{detail.kind === "page" ? "node" : detail.kind}</p>
          <h3>{detail.kind === "page" ? hostname(detail.url) : detail.match || detail.query || "session"}</h3>
        </div>
        <button className="close-btn" type="button" onClick={onClose}>
          Close
        </button>
      </div>

      {detail.kind === "session" ? (
        <>
          <div className="popup-badges">
            <span className={`badge badge-${toneFromStatus(detail.status)}`}>{detail.status}</span>
          </div>
          <dl className="detail-list">
            <dt>Message</dt>
            <dd>{detail.message || "-"}</dd>
            <dt>Current url</dt>
            <dd>{detail.currentUrl || "-"}</dd>
            <dt>Keywords</dt>
            <dd>{detail.stats.keywords}</dd>
            <dt>Roots</dt>
            <dd>{detail.stats.roots}</dd>
            <dt>Visited</dt>
            <dd>{detail.stats.visited}</dd>
            <dt>Official</dt>
            <dd>{detail.stats.official}</dd>
            <dt>Suspicious</dt>
            <dd>{detail.stats.suspicious}</dd>
            <dt>Clean</dt>
            <dd>{detail.stats.clean}</dd>
          </dl>
          {detail.keywords?.length > 0 && (
            <>
              <h4>Keywords</h4>
              <ul className="url-list">
                {detail.keywords.map((keyword) => (
                  <li key={keyword.id}>{keyword.query}</li>
                ))}
              </ul>
            </>
          )}
          {detail.error && <div className="error-banner compact">{detail.error}</div>}
        </>
      ) : (
        <>
          <div className="popup-badges">
            <span className={`badge badge-${normalizeBadgeTone(detail.color, detail.status)}`}>
              {detail.classification || detail.status}
            </span>
            <span className="badge badge-gray">depth {detail.depth}</span>
            {detail.root && <span className="badge badge-blue">root</span>}
          </div>
          <a className="detail-url" href={detail.url} target="_blank" rel="noreferrer">
            {detail.url}
          </a>
          <dl className="detail-list">
            <dt>Title</dt>
            <dd>{detail.title || "-"}</dd>
            <dt>Reason</dt>
            <dd>{detail.reason || "-"}</dd>
            <dt>Status</dt>
            <dd>{detail.status}</dd>
            <dt>Links</dt>
            <dd>{detail.links?.length || 0}</dd>
            <dt>Children</dt>
            <dd>{detail.child_ids?.length || 0}</dd>
            <dt>Iframes</dt>
            <dd>{detail.iframes?.length || 0}</dd>
            <dt>Stream urls</dt>
            <dd>{detail.stream_urls?.length || 0}</dd>
          </dl>
          {detail.summary && (
            <div className="detail-block">
              <strong>Summary</strong>
              <p>{detail.summary}</p>
            </div>
          )}
          {detail.stream_urls?.length > 0 && (
            <>
              <h4>Stream urls</h4>
              <ul className="url-list">
                {detail.stream_urls.slice(0, 3).map((url) => (
                  <li key={url}>
                    <a href={url} target="_blank" rel="noreferrer">
                      {url}
                    </a>
                  </li>
                ))}
              </ul>
            </>
          )}
          {detail.iframes?.length > 0 && (
            <>
              <h4>Iframes</h4>
              <ul className="url-list">
                {detail.iframes.slice(0, 10).map((url) => (
                  <li key={url}>
                    <a href={url} target="_blank" rel="noreferrer">
                      {url}
                    </a>
                  </li>
                ))}
              </ul>
            </>
          )}
          {detail.links?.length > 0 && (
            <>
              <h4>Links</h4>
              <ul className="url-list">
                {detail.links.slice(0, 20).map((link) => (
                  <li key={link.url}>
                    <a href={link.url} target="_blank" rel="noreferrer">
                      {link.title || hostname(link.url)}
                    </a>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </div>
  );
}

function toneFromStatus(status) {
  if (status === "finished") return "green";
  if (status === "failed" || status === "stopped") return "gray";
  return "blue";
}

function normalizeBadgeTone(color, status) {
  if (color === "blue" || color === "red" || color === "green") return color;
  if (status === "error") return "gray";
  return "yellow";
}

function hostname(value) {
  if (!value) return "";
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch {
    return value;
  }
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

createRoot(document.getElementById("root")).render(<App />);
