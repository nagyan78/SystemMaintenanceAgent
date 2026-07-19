<template>
  <section class="card">
    <div class="card-head"><div><p class="eyebrow">版本列表</p><h2>{{ title }}</h2></div></div>
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>对比</th><th>版本号</th><th>说明</th><th>质量分</th><th>校验状态</th><th>生命周期</th><th>来源版本</th><th>节点数</th><th>时间</th></tr></thead>
        <tbody>
          <tr v-for="version in versions" :key="version.id" class="version-row" :data-focused="focusedId === version.id" @click="$emit('focus', version.id)">
            <td><input type="checkbox" :name="name" :value="version.id" :checked="comparisonIds.includes(version.id)" @click.stop @change="$emit('toggle-compare', version.id)" /></td>
            <td>{{ version.version_no }} <span v-if="focusedId === version.id" class="badge" data-tone="success">当前查看</span></td>
            <td>{{ version.description || '-' }}</td><td>{{ version.quality_score ?? '-' }}</td>
            <td><span class="badge" :data-tone="version.verification_status === 'passed' ? 'success' : 'warning'">{{ verificationLabel(version.verification_status) }}</span></td>
            <td><span class="badge" :data-tone="lifecycleTone(version.lifecycle_status)">{{ lifecycleLabel(version.lifecycle_status) }}</span></td>
            <td>{{ version.parent_version_id ? `#${version.parent_version_id}` : '-' }}</td><td>{{ version.node_count ?? '-' }}</td><td>{{ version.created_time || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { VersionRecord } from '../api/versions'
defineProps<{ title: string; name: string; versions: VersionRecord[]; focusedId: number; comparisonIds: number[] }>()
defineEmits<{ focus: [id: number]; 'toggle-compare': [id: number] }>()
function verificationLabel(status?: string | null) { return ({ passed: '已通过', partial: '部分完成', failed: '失败', not_verified: '未校验' } as Record<string, string>)[status || 'not_verified'] || status }
function lifecycleLabel(status?: string | null) { return ({ draft: '草稿', verifying: '复诊中', passed: '复诊通过', partial: '部分通过', failed: '复诊失败', released: '正式发布', superseded: '已被替代' } as Record<string, string>)[status || 'draft'] || status }
function lifecycleTone(status?: string | null) { return ['passed', 'released'].includes(String(status)) ? 'success' : ['failed', 'superseded'].includes(String(status)) ? 'danger' : 'warning' }
</script>

<style scoped>
.version-row{cursor:pointer}.version-row[data-focused='true']{background:rgba(47,111,237,.08)}
</style>
