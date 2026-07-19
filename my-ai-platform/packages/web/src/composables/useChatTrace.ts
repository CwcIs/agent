import { ref } from "vue";

export interface TraceCall {
  id: string;
  agent_id: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  latency_ms: number;
  status: string;
  created_at: string;
}

export interface TraceAgent {
  agent_id: string;
  calls: TraceCall[];
  subtotal: { tokens: number; cost_usd: number; latency_ms: number; call_count: number };
}

export interface TraceData {
  trace_id: string;
  agents: TraceAgent[];
  summary: { total_tokens: number; total_cost_usd: number; total_latency_ms: number; call_count: number };
}

export function useChatTrace() {
  const traceId = ref<string | null>(null);
  const defaultTraceId = ref<string | null>(null);
  const traceExpanded = ref(false);
  const traceData = ref<TraceData | null>(null);
  const traceLoading = ref(false);
  const phaseTraceLabel = ref<string | null>(null);

  async function fetchTrace(requestedId?: string) {
    const targetId = requestedId || traceId.value;
    if (!targetId || traceLoading.value) return;
    traceLoading.value = true;
    try {
      const response = await fetch(`/trace/${targetId}`);
      if (response.ok) traceData.value = await response.json();
    } catch {
      // Trace details are supplementary; chat remains usable when unavailable.
    } finally {
      traceLoading.value = false;
    }
  }

  function toggleTrace() {
    traceExpanded.value = !traceExpanded.value;
    if (traceExpanded.value && !traceData.value) fetchTrace();
  }

  function setActiveTrace(nextTraceId: string | null, options: { expand?: boolean; label?: string | null } = {}) {
    if (!nextTraceId) return;
    traceId.value = nextTraceId;
    defaultTraceId.value = defaultTraceId.value || nextTraceId;
    phaseTraceLabel.value = options.label ?? phaseTraceLabel.value;
    if (options.expand) traceExpanded.value = true;
    traceData.value = null;
    fetchTrace(nextTraceId);
  }

  function onPhaseTraceClick(phaseId: string) {
    if (!defaultTraceId.value) defaultTraceId.value = traceId.value;
    setActiveTrace(phaseId, { expand: true, label: phaseId.slice(0, 8) });
  }

  function resetToGlobalTrace() {
    phaseTraceLabel.value = null;
    traceId.value = defaultTraceId.value;
    traceData.value = null;
    traceExpanded.value = false;
    if (traceId.value) fetchTrace(traceId.value);
  }

  function resetTrace() {
    traceId.value = null;
    defaultTraceId.value = null;
    phaseTraceLabel.value = null;
    traceData.value = null;
    traceExpanded.value = false;
  }

  return {
    traceId,
    traceExpanded,
    traceData,
    traceLoading,
    phaseTraceLabel,
    toggleTrace,
    setActiveTrace,
    onPhaseTraceClick,
    resetToGlobalTrace,
    resetTrace,
  };
}

