<template>
  <section class="card">
    <div class="card-head">
      <div>
        <p class="eyebrow">审核建议</p>
        <h2>{{ title }}</h2>
      </div>
      <span class="badge">{{ suggestions.length }}</span>
    </div>
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th>选择</th>
            <th>状态</th>
            <th>风险</th>
            <th>类型</th>
            <th>目标</th>
            <th>建议</th>
            <th>动作数据</th>
            <th>理由</th>
            <th>确认</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in suggestions" :key="item.id" :data-selected="selectedIds.includes(item.id)">
            <td>
              <input
                type="checkbox"
                :checked="selectedIds.includes(item.id)"
                :disabled="!canSelect(item)"
                @change="canSelect(item) && $emit('toggle', item.id)"
              />
            </td>
            <td><span class="badge" :data-tone="statusTone(item.status)">{{ statusLabel(item.status) }}</span></td>
            <td><span class="risk" :data-tone="item.risk_level">{{ item.risk_level }}</span></td>
            <td>{{ item.action_type }}</td>
            <td>{{ item.target_node_name || item.target_node_id || '-' }}</td>
            <td>{{ item.suggestion }}</td>
            <td><pre class="payload-preview">{{ formatPayload(item.action_payload) }}</pre></td>
            <td>{{ item.reason }}</td>
            <td>{{ item.need_confirm ? '需要' : '可自动通过' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { SuggestionRecord } from '../api/reviews'

defineProps<{ title: string; suggestions: SuggestionRecord[]; selectedIds: number[] }>()
defineEmits<{ toggle: [id: number] }>()

function canSelect(item: SuggestionRecord) {
  return ['pending', 'edited'].includes(item.status)
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: '待审核',
    edited: '已编辑',
    approved: '已批准',
    rejected: '已拒绝',
    executed: '已执行',
    failed: '失败',
  }
  return labels[status] || status
}

function statusTone(status: string) {
  const tones: Record<string, string> = {
    pending: 'warning',
    edited: 'warning',
    approved: 'success',
    executed: 'success',
    rejected: 'danger',
    failed: 'danger',
  }
  return tones[status] || 'neutral'
}

function formatPayload(payload: Record<string, unknown>) {
  const text = JSON.stringify(payload || {}, null, 2)
  return text.length > 220 ? `${text.slice(0, 220)}...` : text
}
</script>
