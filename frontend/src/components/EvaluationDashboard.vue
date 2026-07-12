<template>
  <div class="page-stack">
    <section class="card">
      <div class="card-head"><div><p class="eyebrow">业务质量</p><h2>Golden set 评价</h2></div><span class="badge">{{ gateStatus }}</span></div>
      <div class="review-stats"><span class="badge">Precision {{ pct(m.detection_precision) }}</span><span class="badge">Recall {{ pct(m.detection_recall) }}</span><span class="badge">F1 {{ pct(m.detection_f1) }}</span><span class="badge">动作可执行率 {{ pct(m.action_executable_rate) }}</span><span class="badge" data-tone="danger">危险动作漏拦截率 {{ pct(m.unsafe_action_escape_rate) }}</span></div>
    </section>
    <section class="card"><p class="eyebrow">Agent 质量</p><h2>校准与分流</h2><div class="review-stats"><span class="badge">Triage {{ m.triage_count || 0 }}</span><span class="badge">人工接受率 {{ pct(m.human_accept_rate) }}</span><span class="badge">人工编辑率 {{ pct(m.human_edit_rate) }}</span></div></section>
    <section class="card"><p class="eyebrow">运行成本</p><h2>模型与工具</h2><div class="review-stats"><span class="badge">Model calls {{ m.model_calls || 0 }}</span><span class="badge">Token {{ m.tokens || 0 }}</span><span class="badge">Cache hit {{ pct(m.cache_hit_rate) }}</span><span class="badge">P95 latency {{ m.p95_candidate_latency_ms || 0 }} ms</span></div></section>
  </div>
</template>
<script setup lang="ts">
const props=defineProps<{ metrics:Record<string,any>; gateStatus:string }>(); const m=props.metrics
const pct=(v:any)=>v==null?'—':`${(Number(v)*100).toFixed(1)}%`
</script>
