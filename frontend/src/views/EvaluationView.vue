<template><AppShell><EvaluationDashboard v-if="selected" :metrics="selected.metrics" :gate-status="gateStatus"/><section v-else class="card"><h2>暂无评价结果</h2><p>完成 Golden set 评价后将在这里显示业务质量、Agent 质量和运行成本。</p></section></AppShell></template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'; import AppShell from '../components/AppShell.vue'; import EvaluationDashboard from '../components/EvaluationDashboard.vue'; import { getReleaseGate, listEvaluations } from '../api/evaluations'; import type { EvaluationItem } from '../api/evaluations'
const selected=ref<EvaluationItem|null>(null); const gateStatus=ref('baseline_missing')
onMounted(async()=>{const items=await listEvaluations(); selected.value=items[0]||null; if(selected.value){const gate=await getReleaseGate(selected.value.dataset_version,selected.value.id); gateStatus.value=String(gate.status)}})
</script>
