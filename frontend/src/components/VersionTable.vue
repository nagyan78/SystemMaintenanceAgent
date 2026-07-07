<template>
  <section class="card">
    <div class="card-head">
      <div>
        <p class="eyebrow">版本列表</p>
        <h2>{{ title }}</h2>
      </div>
    </div>
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th>选择</th>
            <th>版本号</th>
            <th>说明</th>
            <th>质量分</th>
            <th>节点数</th>
            <th>时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="version in versions" :key="version.id">
            <td><input type="checkbox" :name="name" :value="version.id" :checked="selectedIds.includes(version.id)" @change="$emit('select', version.id)" /></td>
            <td>{{ version.version_no }}</td>
            <td>{{ version.description || '-' }}</td>
            <td>{{ version.quality_score ?? '-' }}</td>
            <td>{{ version.node_count ?? '-' }}</td>
            <td>{{ version.created_time || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { VersionRecord } from '../api/versions'

defineProps<{ title: string; name: string; versions: VersionRecord[]; selectedIds: number[] }>()
defineEmits<{ select: [id: number] }>()
</script>
