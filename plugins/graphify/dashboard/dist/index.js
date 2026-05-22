(function () {
  "use strict";

  const SDK = window.__AOT_PLUGIN_SDK__;
  if (!SDK || !window.__AOT_PLUGINS__) return;

  const React = SDK.React;
  const h = React.createElement;
  const { useState, useMemo, useEffect, useRef } = SDK.hooks;
  const {
    Card,
    CardHeader,
    CardTitle,
    CardContent,
    Input,
    Button,
    Badge,
  } = SDK.components;

  const API = "/api/plugins/graphify";

  async function fetchJson(path) {
    const token = window.__AOT_SESSION_TOKEN__ || "";
    const headers = token ? { "X-Aot-Session-Token": token } : {};
    const res = await fetch(path, { headers });
    const text = await res.text();
    if (!res.ok) throw new Error(text || res.statusText);
    try {
      return JSON.parse(text);
    } catch (_err) {
      return null;
    }
  }

  function buildGraphParams(rootPath, graphPath) {
    const parts = [];
    if (rootPath) parts.push("root_path=" + encodeURIComponent(rootPath));
    if (graphPath) parts.push("graph_path=" + encodeURIComponent(graphPath));
    return parts.length ? "?" + parts.join("&") : "";
  }

  function buildTraceParams(sessionId) {
    return sessionId ? "?session_id=" + encodeURIComponent(sessionId) : "";
  }

  function calcLayout(nodes, edges, width, height) {
    const safeNodes = Array.isArray(nodes) ? nodes : [];
    const safeEdges = Array.isArray(edges) ? edges : [];
    const n = safeNodes.length;
    const cx = width / 2;
    const cy = height / 2;
    const r = Math.max(120, Math.min(width, height) * 0.34);
    const pos = {};
    for (let i = 0; i < n; i++) {
      const node = safeNodes[i];
      const t = (Math.PI * 2 * i) / Math.max(1, n);
      pos[node.id] = {
        x: cx + Math.cos(t) * r,
        y: cy + Math.sin(t) * r,
      };
    }
    if (n > 0) {
      const pulls = {};
      for (const edge of safeEdges) {
        const s = edge.source;
        const t = edge.target;
        if (!pulls[s]) pulls[s] = { x: 0, y: 0, c: 0 };
        if (!pulls[t]) pulls[t] = { x: 0, y: 0, c: 0 };
        if (pos[s] && pos[t]) {
          pulls[s].x += pos[t].x;
          pulls[s].y += pos[t].y;
          pulls[s].c += 1;
          pulls[t].x += pos[s].x;
          pulls[t].y += pos[s].y;
          pulls[t].c += 1;
        }
      }
      for (const node of safeNodes) {
        const p = pulls[node.id];
        if (!p || !p.c || !pos[node.id]) continue;
        pos[node.id].x = pos[node.id].x * 0.72 + (p.x / p.c) * 0.28;
        pos[node.id].y = pos[node.id].y * 0.72 + (p.y / p.c) * 0.28;
      }
    }
    return pos;
  }

  function parseEdgeMap(edges) {
    const neighbors = new Map();
    for (const edge of edges || []) {
      const s = edge.source;
      const t = edge.target;
      if (!neighbors.has(s)) neighbors.set(s, new Set());
      if (!neighbors.has(t)) neighbors.set(t, new Set());
      neighbors.get(s).add(t);
      neighbors.get(t).add(s);
    }
    return neighbors;
  }

  function GraphCanvas(props) {
    const {
      nodes,
      edges,
      selectedId,
      setSelectedId,
      searchTerm,
    } = props;
    const width = 980;
    const height = 560;
    const svgRef = useRef(null);
    const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });
    const dragRef = useRef(null);
    const positions = useMemo(
      () => calcLayout(nodes, edges, width, height),
      [nodes, edges],
    );
    const neighbors = useMemo(() => parseEdgeMap(edges), [edges]);
    const q = (searchTerm || "").trim().toLowerCase();
    const selectedNeighbors = selectedId ? neighbors.get(selectedId) || new Set() : new Set();

    const onPointerDown = (e) => {
      dragRef.current = {
        id: e.pointerId,
        x: e.clientX,
        y: e.clientY,
        tx: transform.x,
        ty: transform.y,
      };
      e.currentTarget.setPointerCapture(e.pointerId);
    };

    const onPointerMove = (e) => {
      const d = dragRef.current;
      if (!d || d.id !== e.pointerId) return;
      setTransform((prev) => ({
        ...prev,
        x: d.tx + (e.clientX - d.x),
        y: d.ty + (e.clientY - d.y),
      }));
    };

    const onPointerUp = (e) => {
      const d = dragRef.current;
      if (!d || d.id !== e.pointerId) return;
      dragRef.current = null;
      e.currentTarget.releasePointerCapture(e.pointerId);
    };

    const onWheel = (e) => {
      e.preventDefault();
      const rect = svgRef.current.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;
      const nextK = Math.min(3.6, Math.max(0.35, transform.k * (e.deltaY > 0 ? 0.9 : 1.1)));
      const ratio = nextK / transform.k;
      const nx = px - (px - transform.x) * ratio;
      const ny = py - (py - transform.y) * ratio;
      setTransform({ x: nx, y: ny, k: nextK });
    };

    const matchNode = (node) =>
      !q || String(node.label || "").toLowerCase().includes(q) || String(node.id).toLowerCase().includes(q);

    const isNodeDimmed = (node) => {
      if (q && !matchNode(node)) return true;
      if (!selectedId) return false;
      if (node.id === selectedId) return false;
      return !selectedNeighbors.has(node.id);
    };

    const isEdgeHighlighted = (edge) =>
      !!selectedId && (edge.source === selectedId || edge.target === selectedId);

    return h(
      "div",
      { className: "graphify-canvas-wrap" },
      h(
        "svg",
        {
          ref: svgRef,
          className: "graphify-viewport",
          viewBox: `0 0 ${width} ${height}`,
          onWheel: onWheel,
          onPointerDown: onPointerDown,
          onPointerMove: onPointerMove,
          onPointerUp: onPointerUp,
          onPointerCancel: onPointerUp,
        },
        h(
          "g",
          {
            transform: `translate(${transform.x}, ${transform.y}) scale(${transform.k})`,
          },
          (edges || []).map((edge) => {
            const s = positions[edge.source];
            const t = positions[edge.target];
            if (!s || !t) return null;
            return h("line", {
              key: edge.id || `${edge.source}-${edge.target}`,
              className: "graphify-edge" + (isEdgeHighlighted(edge) ? " highlight" : ""),
              x1: s.x,
              y1: s.y,
              x2: t.x,
              y2: t.y,
            });
          }),
          (nodes || []).map((node) => {
            const p = positions[node.id];
            if (!p) return null;
            const selected = node.id === selectedId;
            const dim = isNodeDimmed(node);
            const radius = Math.max(8, Math.min(22, 8 + (node.degree || 0)));
            return h(
              "g",
              {
                key: node.id,
                className:
                  "graphify-node" +
                  (selected ? " selected" : "") +
                  (dim ? " dimmed" : ""),
                onClick: () => setSelectedId(node.id),
              },
              h("circle", {
                cx: p.x,
                cy: p.y,
                r: radius,
                fill: selected ? "var(--color-primary)" : "color-mix(in srgb, var(--color-accent) 42%, transparent)",
                stroke: "color-mix(in srgb, var(--color-foreground) 30%, transparent)",
              }),
              h(
                "text",
                {
                  x: p.x + radius + 4,
                  y: p.y + 4,
                  fill: "var(--color-foreground)",
                  fontSize: 11,
                },
                String(node.label || node.id),
              ),
            );
          }),
        ),
      ),
    );
  }

  function ContextTraceChart({ entries, selectedIndex, setSelectedIndex }) {
    const width = 980;
    const height = 300;
    const chartH = 220;
    const left = 42;
    const top = 24;
    const usableW = width - left - 26;
    const usableH = chartH - top - 18;
    const points = (entries || []).map((entry, idx) => ({
      idx,
      call: Number(entry.call || idx + 1),
      pct: Number(entry.pct || 0),
      compressed: entry.compressed === true,
      attempted: entry.compression_attempted === true || entry.msgs_before_compress != null,
      raw: entry,
    }));
    const maxX = Math.max(1, points.length - 1);
    const x = (i) => left + (i / maxX) * usableW;
    const y = (pct) => top + (1 - Math.max(0, Math.min(100, pct)) / 100) * usableH;
    const path = points
      .map((p, i) => `${i === 0 ? "M" : "L"} ${x(p.idx)} ${y(p.pct)}`)
      .join(" ");

    return h(
      "div",
      { className: "graphify-canvas-wrap" },
      h(
        "svg",
        { className: "graphify-viewport", viewBox: `0 0 ${width} ${height}` },
        h("line", { x1: left, y1: top, x2: left, y2: top + usableH, stroke: "var(--color-border)" }),
        h("line", { x1: left, y1: top + usableH, x2: left + usableW, y2: top + usableH, stroke: "var(--color-border)" }),
        [25, 50, 75, 100].map((tick) =>
          h(
            "g",
            { key: tick },
            h("line", {
              x1: left,
              y1: y(tick),
              x2: left + usableW,
              y2: y(tick),
              stroke: "color-mix(in srgb, var(--color-border) 60%, transparent)",
              strokeDasharray: "4 4",
            }),
            h(
              "text",
              {
                x: 6,
                y: y(tick) + 4,
                fill: "var(--color-muted-foreground)",
                fontSize: 11,
              },
              `${tick}%`,
            ),
          ),
        ),
        h("path", {
          d: path,
          fill: "none",
          stroke: "var(--color-primary)",
          strokeWidth: 2.4,
        }),
        points.map((p) =>
          h("circle", {
            key: `p-${p.idx}`,
            className: "graphify-point",
            cx: x(p.idx),
            cy: y(p.pct),
            r: selectedIndex === p.idx ? 6 : 4,
            fill: p.compressed ? "var(--color-success)" : p.attempted ? "var(--color-warning)" : "var(--color-accent)",
            stroke: "var(--color-card)",
            strokeWidth: 1.2,
            onClick: () => setSelectedIndex(p.idx),
          }),
        ),
        h(
          "text",
          { x: left, y: height - 16, fill: "var(--color-muted-foreground)", fontSize: 11 },
          "Turn progression",
        ),
      ),
    );
  }

  function GraphifyDashboardPage() {
    const [tab, setTab] = useState("knowledge");
    const [rootPath, setRootPath] = useState("");
    const [graphPath, setGraphPath] = useState("");
    const [loadingGraph, setLoadingGraph] = useState(false);
    const [graphError, setGraphError] = useState("");
    const [graphPayload, setGraphPayload] = useState(null);
    const [searchTerm, setSearchTerm] = useState("");
    const [selectedNodeId, setSelectedNodeId] = useState(null);

    const [traces, setTraces] = useState([]);
    const [selectedSession, setSelectedSession] = useState("");
    const [traceLoading, setTraceLoading] = useState(false);
    const [traceError, setTraceError] = useState("");
    const [tracePayload, setTracePayload] = useState(null);
    const [selectedTraceIndex, setSelectedTraceIndex] = useState(-1);
    const pollRef = useRef(null);

    const nodes = (graphPayload && graphPayload.graph && graphPayload.graph.nodes) || [];
    const edges = (graphPayload && graphPayload.graph && graphPayload.graph.edges) || [];
    const neighbors = useMemo(() => parseEdgeMap(edges), [edges]);
    const selectedNode = useMemo(
      () => nodes.find((n) => n.id === selectedNodeId) || null,
      [nodes, selectedNodeId],
    );

    const loadGraph = async () => {
      setLoadingGraph(true);
      setGraphError("");
      try {
        const params = buildGraphParams(rootPath.trim(), graphPath.trim());
        const payload = await fetchJson(`${API}/graph${params}`);
        setGraphPayload(payload);
        if (payload && payload.graph && payload.graph.nodes && payload.graph.nodes.length) {
          setSelectedNodeId(payload.graph.nodes[0].id);
        } else {
          setSelectedNodeId(null);
        }
      } catch (err) {
        setGraphError(String(err && err.message ? err.message : err));
      } finally {
        setLoadingGraph(false);
      }
    };

    const loadTraceList = async () => {
      try {
        const payload = await fetchJson(`${API}/context-trace/list`);
        setTraces((payload && payload.traces) || []);
      } catch (_err) {
      }
    };

    const loadLatestTrace = async (sessionId) => {
      setTraceLoading(true);
      setTraceError("");
      try {
        const payload = await fetchJson(`${API}/context-trace/latest${buildTraceParams(sessionId)}`);
        setTracePayload(payload);
        if (!selectedSession && payload && payload.session_id) {
          setSelectedSession(payload.session_id);
        }
        const entries = (payload && payload.entries) || [];
        setSelectedTraceIndex(entries.length ? entries.length - 1 : -1);
      } catch (err) {
        setTraceError(String(err && err.message ? err.message : err));
      } finally {
        setTraceLoading(false);
      }
    };

    useEffect(() => {
      loadGraph();
      loadTraceList();
      loadLatestTrace("");
    }, []);

    useEffect(() => {
      if (tab !== "context") return;
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(() => {
        loadTraceList();
        loadLatestTrace(selectedSession || "");
      }, 3000);
      return () => {
        if (pollRef.current) clearInterval(pollRef.current);
      };
    }, [tab, selectedSession]);

    const selectedTraceEntry =
      tracePayload &&
      tracePayload.entries &&
      selectedTraceIndex >= 0 &&
      selectedTraceIndex < tracePayload.entries.length
        ? tracePayload.entries[selectedTraceIndex]
        : null;

    const selectedNeighbors = selectedNode
      ? Array.from(neighbors.get(selectedNode.id) || [])
      : [];

    return h(
      "div",
      { className: "graphify-page" },
      h(
        Card,
        null,
        h(CardHeader, null, h(CardTitle, null, "Graphify Interactive Viewer")),
        h(
          CardContent,
          null,
          h(
            "div",
            { className: "graphify-tabs" },
            h(
              Button,
              { onClick: () => setTab("knowledge"), active: tab === "knowledge" },
              "Knowledge Graph",
            ),
            h(
              Button,
              { onClick: () => setTab("context"), active: tab === "context" },
              "Live Context Window",
            ),
          ),
          tab === "knowledge"
            ? h(
                "div",
                { style: { marginTop: "10px" } },
                h(
                  "div",
                  { className: "graphify-toolbar" },
                  h(
                    "div",
                    { className: "graphify-field" },
                    h("label", null, "Repository path"),
                    h(Input, {
                      value: rootPath,
                      onChange: (e) => setRootPath(e.target.value),
                      placeholder: "/path/to/repo",
                    }),
                  ),
                  h(
                    "div",
                    { className: "graphify-field" },
                    h("label", null, "Graph JSON path (optional)"),
                    h(Input, {
                      value: graphPath,
                      onChange: (e) => setGraphPath(e.target.value),
                      placeholder: "/path/to/graphify-out/graph.json",
                    }),
                  ),
                  h(
                    "div",
                    { className: "graphify-field" },
                    h("label", null, "Search nodes"),
                    h(Input, {
                      value: searchTerm,
                      onChange: (e) => setSearchTerm(e.target.value),
                      placeholder: "AuthService",
                    }),
                  ),
                  h(
                    Button,
                    { onClick: loadGraph, disabled: loadingGraph },
                    loadingGraph ? "Loading..." : "Load graph",
                  ),
                ),
                graphError ? h("p", { style: { color: "var(--color-destructive)" } }, graphError) : null,
                h(
                  "div",
                  { className: "graphify-grid", style: { marginTop: "8px" } },
                  h(GraphCanvas, {
                    nodes,
                    edges,
                    selectedId: selectedNodeId,
                    setSelectedId: setSelectedNodeId,
                    searchTerm,
                  }),
                  h(
                    "div",
                    { className: "graphify-side" },
                    h(
                      Card,
                      null,
                      h(CardHeader, null, h(CardTitle, null, "Graph Summary")),
                      h(
                        CardContent,
                        null,
                        h(Badge, null, `Nodes: ${nodes.length}`),
                        " ",
                        h(Badge, null, `Edges: ${edges.length}`),
                        graphPayload && graphPayload.source_path
                          ? h("p", { style: { marginTop: "8px", opacity: 0.75 } }, graphPayload.source_path)
                          : null,
                      ),
                    ),
                    h(
                      Card,
                      null,
                      h(CardHeader, null, h(CardTitle, null, "Selected Node")),
                      h(
                        CardContent,
                        null,
                        selectedNode
                          ? h(
                              React.Fragment,
                              null,
                              h("p", null, h("strong", null, selectedNode.label)),
                              h("p", null, `ID: ${selectedNode.id}`),
                              h("p", null, `Type: ${selectedNode.type}`),
                              h("p", null, `Degree: ${selectedNode.degree}`),
                              h("p", { style: { marginTop: "8px", marginBottom: "4px" } }, "Neighbors"),
                              h(
                                "div",
                                { className: "graphify-list" },
                                selectedNeighbors.length
                                  ? selectedNeighbors.map((id) =>
                                      h(
                                        "button",
                                        { key: id, onClick: () => setSelectedNodeId(id) },
                                        id,
                                      ),
                                    )
                                  : h("div", { style: { padding: "8px", opacity: 0.65 } }, "No neighbors"),
                              ),
                            )
                          : h("p", { style: { opacity: 0.7 } }, "Select a node to inspect relationships."),
                      ),
                    ),
                  ),
                ),
              )
            : h(
                "div",
                { style: { marginTop: "10px" } },
                h(
                  "div",
                  { className: "graphify-toolbar" },
                  h(
                    "div",
                    { className: "graphify-field" },
                    h("label", null, "Trace session"),
                    h(
                      "select",
                      {
                        value: selectedSession,
                        onChange: (e) => {
                          setSelectedSession(e.target.value);
                          loadLatestTrace(e.target.value);
                        },
                      },
                      h("option", { value: "" }, "Latest"),
                      traces.map((trace) =>
                        h(
                          "option",
                          { key: trace.session_id, value: trace.session_id },
                          trace.session_id,
                        ),
                      ),
                    ),
                  ),
                  h(
                    Button,
                    { onClick: () => loadLatestTrace(selectedSession || ""), disabled: traceLoading },
                    traceLoading ? "Refreshing..." : "Refresh",
                  ),
                ),
                traceError ? h("p", { style: { color: "var(--color-destructive)" } }, traceError) : null,
                tracePayload
                  ? h(
                      "div",
                      { className: "graphify-grid", style: { marginTop: "8px" } },
                      h(ContextTraceChart, {
                        entries: tracePayload.entries || [],
                        selectedIndex: selectedTraceIndex,
                        setSelectedIndex: setSelectedTraceIndex,
                      }),
                      h(
                        "div",
                        { className: "graphify-side" },
                        h(
                          Card,
                          null,
                          h(CardHeader, null, h(CardTitle, null, "Trace Summary")),
                          h(
                            CardContent,
                            null,
                            h(Badge, null, `Calls: ${tracePayload.summary.total_calls}`),
                            " ",
                            h(Badge, null, `Peak: ${tracePayload.summary.peak_pct.toFixed(1)}%`),
                            " ",
                            h(Badge, null, `Attempts: ${tracePayload.summary.compression_attempts}`),
                            " ",
                            h(Badge, null, `Successes: ${tracePayload.summary.successful_compressions}`),
                            h("p", { style: { marginTop: "8px", opacity: 0.75 } }, tracePayload.session_id),
                          ),
                        ),
                        h(
                          Card,
                          null,
                          h(CardHeader, null, h(CardTitle, null, "Selected Turn")),
                          h(
                            CardContent,
                            null,
                            selectedTraceEntry
                              ? h(
                                  React.Fragment,
                                  null,
                                  h("p", null, `Call: ${selectedTraceEntry.call}`),
                                  h("p", null, `Messages: ${selectedTraceEntry.msgs}`),
                                  h("p", null, `Tokens: ${selectedTraceEntry.tokens}`),
                                  h("p", null, `Threshold: ${selectedTraceEntry.threshold}`),
                                  h("p", null, `Usage: ${selectedTraceEntry.pct}%`),
                                  h("p", null, `Compression count: ${selectedTraceEntry.compressions || 0}`),
                                  h("p", null, `Attempted: ${selectedTraceEntry.compression_attempted ? "yes" : "no"}`),
                                  h("p", null, `Succeeded: ${selectedTraceEntry.compressed ? "yes" : "no"}`),
                                )
                              : h("p", { style: { opacity: 0.7 } }, "Select a point to inspect turn details."),
                          ),
                        ),
                      ),
                    )
                  : h("p", { style: { opacity: 0.7 } }, "No trace loaded yet."),
              ),
        ),
      ),
    );
  }

  window.__AOT_PLUGINS__.register("graphify", GraphifyDashboardPage);
})();
