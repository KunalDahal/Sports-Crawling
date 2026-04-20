import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8080";

const emptyForm = {
  keyword: "",
  api_key: "",
  db_name: "sports_scraper",
  mongo_uri: "mongodb://localhost:27017",
  proxy_url: "",
};

const lanes = {
  session: 0,
  search: 1,
  crawl: 2,
  llm: 3,
  stream: 4,
  db: 5,
  runner: 6,
  error: 6,
};

const eventLabels = {
  "session.created": "Session created",
  "session.finished": "Session finished",
  "search.start": "Search started",
  "search.turn_done": "Search turn",
  "search.complete": "Search complete",
  "search.candidates": "Candidates",
  "crawl.tree_start": "Tree started",
  "crawl.tree_done": "Tree finished",
  "crawl.page_start": "Page opened",
  "crawl.page_done": "Page scored",
  "crawl.page_fail": "Page failed",
  "llm.navigate": "LLM navigate",
  "llm.score": "LLM score",
  "llm.verify_live": "Verify stream",
  "llm.ad_check": "Ad check",
  "stream.found": "Stream found",
  "stream.rejected": "Stream rejected",
  "db.node_upserted": "DB node",
  "db.stream_recorded": "DB stream",
  "runner.finished": "Runner finished",
  "runner.error": "Runner error",
  error: "Crawler error",
};

function App() {
  const [form, setForm] = useState(emptyForm);
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState("");
  const [events, setEvents] = useState([]);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    refreshSessions();
    const timer = setInterval(refreshSessions, 3000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!activeId) return;
    setEvents([]);
    setSelected(null);
    const source = new EventSource(`${API_BASE}/api/sessions/${activeId}/events`);
    source.addEventListener("crawler", (message) => {
      const event = JSON.parse(message.data);
      setEvents((current) => [...current.slice(-499), event]);
    });
    source.onerror = () => setError("Live event stream disconnected. Reopening usually happens automatically.");
    return () => source.close();
  }, [activeId]);

  async function refreshSessions() {
    try {
      const res = await fetch(`${API_BASE}/api/sessions`);
      if (!res.ok) return;
      const data = await res.json();
      setSessions(data);
      if (!activeId && data.length) setActiveId(data[0].id);
    } catch {
      // The backend might not be running yet; the UI remains usable.
    }
  }

  async function startSession(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not start scraper");
      setActiveId(data.id);
      setEvents([]);
      setForm((current) => ({ ...current, keyword: "" }));
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

  const active = sessions.find((session) => session.id === activeId);
  const graph = useMemo(() => buildGraph(events), [events]);

  return (
    <main className="shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">spcrawler console</p>
          <h1>Live scraper sessions</h1>
        </div>
        <div className="health">
          <span className="pulse" />
          {active ? active.status : "waiting"}
        </div>
      </section>

      <section className="workspace">
        <aside className="side">
          <form className="launcher" onSubmit={startSession}>
            <label>
              Keyword
              <input
                value={form.keyword}
                onChange={(e) => setForm({ ...form, keyword: e.target.value })}
                placeholder="India vs Australia live stream"
                required
              />
            </label>
            <label>
              Gemini API key
              <input
                type="password"
                value={form.api_key}
                onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                placeholder="Paste key for this run"
              />
            </label>
            <label>
              Database name
              <input
                value={form.db_name}
                onChange={(e) => setForm({ ...form, db_name: e.target.value })}
              />
            </label>
            <label>
              Mongo URI
              <input
                value={form.mongo_uri}
                onChange={(e) => setForm({ ...form, mongo_uri: e.target.value })}
              />
            </label>
            <label>
              Proxy URL
              <input
                value={form.proxy_url}
                onChange={(e) => setForm({ ...form, proxy_url: e.target.value })}
                placeholder="http://user:pass@host:port"
              />
            </label>
            <button disabled={busy}>{busy ? "Starting..." : "Start scraper"}</button>
          </form>

          {error && <div className="error">{error}</div>}

          <div className="sessions">
            <h2>Sessions</h2>
            {sessions.length === 0 && <p className="muted">No sessions yet.</p>}
            {sessions.map((session) => (
              <button
                className={`session ${session.id === activeId ? "active" : ""}`}
                key={session.id}
                onClick={() => setActiveId(session.id)}
                type="button"
              >
                <span>{session.keyword}</span>
                <small>{session.status} / {session.events} events</small>
              </button>
            ))}
          </div>
        </aside>

        <section className="mainstage">
          <Stats active={active} />
          <NodeCanvas graph={graph} onSelect={setSelected} selected={selected} />
        </section>

        <aside className="inspector">
          <div className="inspect-head">
            <h2>Event details</h2>
            {active && ["running", "starting"].includes(active.status) && (
              <button className="ghost" onClick={() => stopSession(active.id)} type="button">
                Stop
              </button>
            )}
          </div>
          {selected ? (
            <EventDetails event={selected} />
          ) : (
            <p className="muted">Select a node to inspect its latest payload.</p>
          )}
          <div className="event-feed">
            <h2>Latest events</h2>
            {events.slice(-12).reverse().map((event, index) => (
              <button key={`${event.ts}-${index}`} onClick={() => setSelected(event)} type="button">
                <span>{eventLabels[event.type] || event.type}</span>
                <small>{event.type}</small>
              </button>
            ))}
          </div>
        </aside>
      </section>
    </main>
  );
}

function Stats({ active }) {
  const values = [
    ["Pages", active?.pages_crawled ?? 0],
    ["Streams", active?.streams_found ?? 0],
    ["Search results", active?.search_results ?? 0],
    ["Candidates", active?.candidates_registered ?? 0],
  ];

  return (
    <div className="stats">
      {values.map(([label, value]) => (
        <div className="stat" key={label}>
          <strong>{value}</strong>
          <span>{label}</span>
        </div>
      ))}
      <div className="current-url">
        <span>Current URL</span>
        <strong>{active?.current_url || "Waiting for crawler activity"}</strong>
      </div>
    </div>
  );
}

function NodeCanvas({ graph, onSelect, selected }) {
  return (
    <div className="canvas" style={{ minHeight: graph.height }}>
      <svg className="edges" width={graph.width} height={graph.height} viewBox={`0 0 ${graph.width} ${graph.height}`}>
        {graph.edges.map((edge) => (
          <path key={edge.id} d={edge.path} />
        ))}
      </svg>
      {graph.nodes.map((node) => (
        <button
          className={`node ${node.kind} ${selected === node.event ? "selected" : ""}`}
          key={node.id}
          onClick={() => onSelect(node.event)}
          style={{ left: node.x, top: node.y }}
          type="button"
        >
          <span className="node-type">{node.type}</span>
          <strong>{node.title}</strong>
          <small>{node.subtitle}</small>
        </button>
      ))}
      {graph.nodes.length === 0 && (
        <div className="empty">
          <img
            alt=""
            src="https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=900&q=70"
          />
          <p>Start a scraper and the graph will wake up as events arrive.</p>
        </div>
      )}
    </div>
  );
}

function EventDetails({ event }) {
  return (
    <div className="details">
      <p className="eyebrow">{event.type}</p>
      <h3>{eventLabels[event.type] || event.type}</h3>
      <dl>
        <dt>Session</dt>
        <dd>{event.session_id || "pending"}</dd>
        <dt>Time</dt>
        <dd>{event.ts || "now"}</dd>
      </dl>
      <pre>{JSON.stringify(event.data, null, 2)}</pre>
    </div>
  );
}

function buildGraph(events) {
  const nodes = [];
  const edges = [];
  const latestByKey = new Map();
  const seenCounts = new Map();

  events.forEach((event) => {
    const key = nodeKey(event);
    latestByKey.set(key, event);
    seenCounts.set(key, (seenCounts.get(key) || 0) + 1);
  });

  let index = 0;
  for (const [key, event] of latestByKey.entries()) {
    const kind = event.type.split(".")[0];
    const lane = lanes[kind] ?? 6;
    const column = index % 8;
    const rowBump = Math.floor(index / 8) * 120;
    nodes.push({
      id: key,
      event,
      kind,
      type: kind,
      title: eventLabels[event.type] || event.type,
      subtitle: subtitleFor(event, seenCounts.get(key)),
      x: 28 + column * 190,
      y: 28 + lane * 118 + rowBump,
      cx: 104 + column * 190,
      cy: 74 + lane * 118 + rowBump,
    });
    index++;
  }

  const byID = new Map(nodes.map((node) => [node.id, node]));
  let lastNode = null;
  for (const event of events) {
    const node = byID.get(nodeKey(event));
    if (!node) continue;
    if (lastNode && lastNode.id !== node.id) {
      edges.push(edgeBetween(lastNode, node, edges.length));
    }
    lastNode = node;
  }

  const height = Math.max(640, ...nodes.map((node) => node.y + 120));
  return { nodes, edges, width: 1600, height };
}

function edgeBetween(a, b, index) {
  const mid = (a.cy + b.cy) / 2;
  return {
    id: `${a.id}-${b.id}-${index}`,
    path: `M ${a.cx} ${a.cy} C ${a.cx + 70} ${mid}, ${b.cx - 70} ${mid}, ${b.cx} ${b.cy}`,
  };
}

function nodeKey(event) {
  const data = event.data || {};
  if (data.stream_url) return `${event.type}:${data.stream_url}`;
  if (data.url) return `${event.type}:${data.url}`;
  if (data.start_url) return `${event.type}:${data.start_url}`;
  if (data.tree_col) return `${event.type}:${data.tree_col}`;
  return `${event.type}:${event.session_id || "runner"}`;
}

function subtitleFor(event, count) {
  const data = event.data || {};
  const text = data.url || data.stream_url || data.query || data.keyword || data.context || "";
  const suffix = count > 1 ? ` / ${count} updates` : "";
  return `${shorten(text || event.session_id || "event", 58)}${suffix}`;
}

function shorten(value, size) {
  if (!value) return "";
  return value.length > size ? `${value.slice(0, size - 1)}...` : value;
}

createRoot(document.getElementById("root")).render(<App />);
