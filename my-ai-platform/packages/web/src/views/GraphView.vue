<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from "vue";
import * as d3 from "d3";

interface GraphNode {
  id: string;
  title: string;
  tags: string[];
  status: string;
  connection_count: number;
  created_at: string;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
  vx?: number;
  vy?: number;
}

interface GraphEdge {
  id: string;
  from_id: string;
  to_id: string;
  relation: string;
  confidence: number;
  source: string;
  status: string;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

const emit = defineEmits<{
  selectNote: [noteId: string];
}>();

const graph = ref<GraphData>({ nodes: [], edges: [] });
const loading = ref(true);
const searchQuery = ref("");
const centerNoteId = ref("");
const depth = ref(2);

const container = ref<HTMLDivElement | null>(null);
const svg = ref<SVGSVGElement | null>(null) as any;

let simulation: any = null;

const RELATION_COLORS: Record<string, string> = {
  wikilink: "#7C9CFF",
  evolved_from: "#70E0A3",
  supersedes: "#FFB86B",
  contradicts: "#FF6B6B",
  similar: "#C084FC",
  related: "#9AA4B2",
};

const TAG_COLORS = ["#7C9CFF", "#70E0A3", "#FFB86B", "#FF6B6B", "#C084FC", "#60A5FA", "#34D399", "#FBBF24"];

function tagColor(node: GraphNode): string {
  const tag = node.tags?.[0];
  if (!tag) return "#5A6278";
  let hash = 0;
  for (let i = 0; i < tag.length; i++) hash = tag.charCodeAt(i) + ((hash << 5) - hash);
  return TAG_COLORS[Math.abs(hash) % TAG_COLORS.length];
}

async function loadGraph(centerId = "", d = 2) {
  loading.value = true;
  try {
    const params = new URLSearchParams();
    if (centerId) { params.set("center_id", centerId); params.set("depth", String(d)); }
    const resp = await fetch(`/notes/graph?${params.toString()}`);
    if (resp.ok) graph.value = await resp.json();
  } catch { /* ignore */ }
  loading.value = false;
  await nextTick();
  renderForce();
}

function renderForce() {
  const el = container.value;
  if (!el || !graph.value.nodes.length) return;

  const W = el.clientWidth;
  const H = el.clientHeight || 600;

  d3.select(svg.value).selectAll("*").remove();

  const svgEl = d3.select(svg.value)
    .attr("width", W)
    .attr("height", H);

  const g = svgEl.append("g");

  // Zoom
  (svgEl as any).call(
    d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on("zoom", (event: any) => g.attr("transform", event.transform))
  );

  // Filter visible edges
  const nodeIds = new Set(graph.value.nodes.map(n => n.id));
  const visibleEdges = graph.value.edges.filter(
    e => nodeIds.has(e.from_id) && nodeIds.has(e.to_id)
  );

  // Edge lines
  const link = g.append("g").selectAll<SVGLineElement, GraphEdge>("line")
    .data(visibleEdges)
    .join("line")
    .attr("stroke", d => RELATION_COLORS[d.relation] || "#5A6278")
    .attr("stroke-opacity", d => d.status === "suggested" ? 0.25 : 0.4)
    .attr("stroke-width", d => d.status === "suggested" ? 1 : 1.5)
    .attr("stroke-dasharray", d => d.status === "suggested" ? "4 4" : "");

  // Nodes
  const node = g.append("g").selectAll<SVGGElement, GraphNode>("g")
    .data(graph.value.nodes)
    .join("g")
    .call(
      d3.drag<SVGGElement, GraphNode>()
        .on("start", (event, d) => {
          if (!event.active) simulation?.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on("drag", (event, d) => {
          d.fx = event.x; d.fy = event.y;
        })
        .on("end", (event, d) => {
          if (!event.active) simulation?.alphaTarget(0);
          d.fx = null; d.fy = null;
        })
    );

  // Circle
  node.append("circle")
    .attr("r", d => Math.max(6, Math.min(20, 6 + d.connection_count * 2.5)))
    .attr("fill", d => tagColor(d))
    .attr("fill-opacity", 0.8)
    .attr("stroke", d => d3.color(tagColor(d))?.darker(0.5)?.toString() || "#333")
    .attr("stroke-width", 1.5);

  // Label
  node.append("text")
    .text(d => d.title.length > 10 ? d.title.slice(0, 10) + "…" : d.title)
    .attr("dx", d => Math.max(8, 6 + d.connection_count * 2.5) + 4)
    .attr("dy", ".35em")
    .attr("fill", "var(--text-secondary, #9AA4B2)")
    .attr("font-size", "9px")
    .attr("font-family", "ui-sans-serif, system-ui, sans-serif");

  // Click handler
  node.on("click", (_, d) => {
    if (centerNoteId.value === d.id) {
      emit("selectNote", d.id);
    } else {
      centerNoteId.value = d.id;
      loadGraph(d.id, depth.value);
    }
  });

  node.append("title").text(d => d.title);

  // Force simulation
  simulation = d3.forceSimulation(graph.value.nodes as any)
    .force("link", d3.forceLink(visibleEdges as any).id((d: any) => d.id).distance(80))
    .force("charge", d3.forceManyBody().strength(-200))
    .force("center", d3.forceCenter(W / 2, H / 2))
    .force("collision", d3.forceCollide().radius((d: any) => Math.max(8, 6 + (d.connection_count || 0) * 2.5) + 10));

  (simulation as any).on("tick", () => {
    link.attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y);
    node.attr("transform", (d: any) => `translate(${d.x},${d.y})`);
  });
}

function handleResize() { renderForce(); }

onMounted(() => {
  loadGraph();
  window.addEventListener("resize", handleResize);
});

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
  simulation?.stop();
});

function focusSearch() {
  if (!searchQuery.value.trim()) return;
  // Search by title match and center on first matching node
  const match = graph.value.nodes.find(n =>
    n.title.toLowerCase().includes(searchQuery.value.toLowerCase())
  );
  if (match) {
    centerNoteId.value = match.id;
    loadGraph(match.id, depth.value);
  }
}

watch(depth, (d) => {
  if (centerNoteId.value) loadGraph(centerNoteId.value, d);
});
</script>

<template>
  <div class="flex flex-col h-full min-h-0" style="color: var(--text-primary); background: var(--bg-app)">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-2.5 border-b shrink-0 gap-3" style="border-color: var(--border-subtle)">
      <div class="flex items-center gap-2">
        <span class="text-xs font-semibold uppercase tracking-wider" style="color: var(--text-muted)">Knowledge Graph</span>
        <span class="text-[10px] px-1.5 py-0.5 rounded-full" style="background: rgba(255,255,255,0.05); color: var(--text-muted)">
          {{ graph.nodes.length }} nodes · {{ graph.edges.length }} edges
        </span>
      </div>

      <div class="flex items-center gap-2">
        <!-- Search -->
        <div class="flex items-center gap-1">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search note…"
            class="text-[10px] px-2 py-1 rounded border bg-transparent outline-none w-28"
            style="color: var(--text-primary); border-color: var(--border-subtle)"
            @keydown.enter="focusSearch"
          />
          <button
            class="text-[10px] px-2 py-1 rounded border hover:brightness-110 transition-all"
            style="color: var(--text-muted); border-color: var(--border-subtle)"
            @click="focusSearch"
          >Find</button>
        </div>

        <!-- Depth -->
        <select
          v-model="depth"
          class="text-[10px] px-1.5 py-1 rounded border bg-transparent outline-none"
          style="color: var(--text-muted); border-color: var(--border-subtle)"
        >
          <option :value="1">1 hop</option>
          <option :value="2">2 hops</option>
          <option :value="3">3 hops</option>
        </select>

        <!-- Reset -->
        <button
          class="text-[10px] px-2 py-1 rounded border hover:brightness-110 transition-all"
          style="color: var(--text-muted); border-color: var(--border-subtle)"
          @click="centerNoteId = ''; loadGraph('')"
        >Reset</button>
      </div>
    </div>

    <!-- Legend -->
    <div class="flex flex-wrap gap-2 px-4 py-1.5 border-b shrink-0" style="border-color: var(--border-subtle)">
      <span
        v-for="(color, rel) in RELATION_COLORS"
        :key="rel"
        class="text-[9px] flex items-center gap-1"
        style="color: var(--text-tertiary)"
      >
        <span class="w-2.5 h-0.5 rounded-full shrink-0" :style="{ background: color }" />
        {{ rel }}
      </span>
    </div>

    <!-- Graph Container -->
    <div ref="container" class="flex-1 min-h-0 relative">
      <div v-if="loading" class="absolute inset-0 flex items-center justify-center">
        <span class="text-xs" style="color: var(--text-muted)">Loading graph…</span>
      </div>
      <div v-else-if="!graph.nodes.length" class="absolute inset-0 flex items-center justify-center">
        <span class="text-xs" style="color: var(--text-tertiary)">
          No notes in graph. Create some notes with [[wikilinks]] or relations first.
        </span>
      </div>
      <svg ref="svg" class="w-full h-full" />
    </div>

    <!-- Hint -->
    <div class="px-4 py-1.5 border-t shrink-0 text-[9px]" style="color: var(--text-tertiary); border-color: var(--border-subtle)">
      Click node to expand · Double-click to open detail · Drag to rearrange · Scroll to zoom
    </div>
  </div>
</template>
