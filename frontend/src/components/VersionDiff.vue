<template>
  <section class="card diff-card">
    <div class="card-head">
      <div>
        <p class="eyebrow">版本对比</p>
        <h2>{{ title }}</h2>
      </div>
      <span class="badge">{{ diffLabel }}</span>
    </div>

    <div v-if="summaryText" class="diff-summary">{{ summaryText }}</div>

    <div v-for="group in groups" :key="group.key" class="diff-section">
      <details open class="diff-details">
        <summary class="diff-summary-head">
          <span class="diff-kind" :data-kind="group.key">{{ kindLabel(group.key) }}</span>
          <span class="diff-count">{{ group.items.length }}</span>
          <span class="diff-kind-text">{{ group.label }}</span>
        </summary>
        <div class="hunks">
          <article v-for="(item, index) in group.items" :key="index" class="hunk" :data-kind="group.key">
            <div class="hunk-head">{{ itemTitle(item) }}</div>
            <div class="hunk-body">
              <template v-if="group.key === 'synonym_changed' && hasCompare(item)">
                <div class="diff-compare">
                  <div class="compare-col old">
                    <div class="compare-tag">修改前</div>
                    <div class="compare-val">{{ asText(item.old ?? item.old_synonyms ?? item.from) }}</div>
                  </div>
                  <div class="compare-arrow">→</div>
                  <div class="compare-col new">
                    <div class="compare-tag">修改后</div>
                    <div class="compare-val">{{ asText(item.new ?? item.new_synonyms ?? item.to) }}</div>
                  </div>
                </div>
              </template>
              <template v-else-if="(group.key === 'renamed' || group.key === 'moved') && hasCompare(item)">
                <div class="diff-move">
                  <code>{{ asText(item.from ?? item.old) }}</code>
                  <span class="move-arrow">→</span>
                  <code>{{ asText(item.to ?? item.new) }}</code>
                </div>
              </template>
              <template v-else>
                <div
                  v-for="(entry, i) in itemRows(item)"
                  :key="i"
                  class="diff-row"
                  :class="group.key === 'added' ? 'add' : group.key === 'deleted' ? 'del' : ''"
                >
                  <span class="sign">{{ group.key === 'added' ? '+' : group.key === 'deleted' ? '−' : '' }}</span>
                  <span class="k">{{ entry[0] }}</span>
                  <span class="v">{{ entry[1] }}</span>
                </div>
              </template>
            </div>
          </article>
        </div>
      </details>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  title: string
  diffLabel: string
  groups: Array<{ key: string; label: string; items: Array<Record<string, unknown>> }>
}>()

const META_KEYS = new Set(['id', 'category_id', 'from', 'to', 'old', 'new', 'old_synonyms', 'new_synonyms'])
const TITLE_KEYS = ['category_path', 'node_name', 'name', 'path', 'label', 'title']

function asText(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function hasCompare(item: Record<string, unknown>): boolean {
  return 'old' in item || 'new' in item || 'old_synonyms' in item || 'new_synonyms' in item || ('from' in item && 'to' in item)
}

function itemTitle(item: Record<string, unknown>): string {
  for (const key of TITLE_KEYS) {
    if (item[key] != null && typeof item[key] !== 'object') return String(item[key])
  }
  if (item.category_id != null) return `节点 #${item.category_id}`
  const firstKey = Object.keys(item).find((k) => !META_KEYS.has(k) && item[k] != null)
  return firstKey ? String(item[firstKey]) : '未命名节点'
}

function itemRows(item: Record<string, unknown>): Array<[string, string]> {
  const rows: Array<[string, string]> = []
  for (const [key, value] of Object.entries(item)) {
    if (key === 'category_path' || key === 'node_name' || key === 'name') continue
    if (META_KEYS.has(key)) continue
    rows.push([key, asText(value)])
  }
  if (rows.length === 0) rows.push(['值', asText(item)])
  return rows
}

function kindLabel(key: string): string {
  const map: Record<string, string> = {
    added: 'A',
    deleted: 'D',
    renamed: 'R',
    moved: 'M',
    synonym_changed: 'S',
  }
  return map[key] ?? '·'
}

const summaryText = computed(() => {
  const parts = props.groups
    .filter((g) => g.items.length > 0)
    .map((g) => `${g.items.length} ${g.label}`)
  if (parts.length === 0) return '无变更'
  const total = props.groups.reduce((sum, g) => sum + g.items.length, 0)
  return `共 ${total} 项变更：${parts.join('，')}`
})
</script>

<style scoped>
.diff-card { max-width: 920px; }
.diff-summary { display: inline-flex; align-items: center; gap: 8px; margin-bottom: 16px; padding: 8px 14px; border-radius: 999px; background: rgba(17,24,39,0.05); font-size: 13px; color: var(--muted); }
.diff-details { border: 1px solid var(--line); border-radius: 14px; padding: 0; margin-bottom: 12px; overflow: hidden; background: var(--surface-solid); }
.diff-summary-head { display: flex; align-items: center; gap: 10px; padding: 12px 16px; cursor: pointer; list-style: none; user-select: none; }
.diff-summary-head::-webkit-details-marker { display: none; }
.diff-kind { width: 22px; height: 22px; border-radius: 6px; display: grid; place-items: center; font-weight: 700; font-size: 12px; color: #fff; flex: none; }
.diff-kind[data-kind='added'] { background: var(--success); }
.diff-kind[data-kind='deleted'] { background: var(--danger); }
.diff-kind[data-kind='renamed'] { background: #d97706; }
.diff-kind[data-kind='moved'] { background: #d97706; }
.diff-kind[data-kind='synonym_changed'] { background: #0a84ff; }
.diff-count { font-weight: 700; }
.diff-kind-text { color: var(--muted); font-size: 13px; }
.hunks { display: grid; gap: 1px; background: var(--line); border-top: 1px solid var(--line); }
.hunk { background: var(--surface-solid); }
.hunk-head { padding: 8px 16px; font-weight: 600; font-size: 13px; background: rgba(17,24,39,0.03); border-bottom: 1px solid var(--line); }
.hunk-body { padding: 6px 0; }
.diff-row { display: grid; grid-template-columns: 22px 160px 1fr; gap: 10px; padding: 4px 16px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; }
.diff-row .sign { color: var(--muted); text-align: center; }
.diff-row .k { color: var(--muted); }
.diff-row .v { color: var(--text); word-break: break-word; }
.diff-row.add { background: rgba(26,127,55,0.08); }
.diff-row.add .sign, .diff-row.add .k { color: var(--success); }
.diff-row.del { background: rgba(217,45,32,0.07); }
.diff-row.del .sign, .diff-row.del .k { color: var(--danger); }
.diff-compare { display: grid; grid-template-columns: 1fr 28px 1fr; gap: 0; padding: 8px 16px; }
.compare-col { padding: 8px 10px; border-radius: 8px; }
.compare-col.old { background: rgba(217,45,32,0.07); }
.compare-col.new { background: rgba(26,127,55,0.08); }
.compare-tag { font-size: 11px; color: var(--muted); margin-bottom: 4px; }
.compare-val { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; word-break: break-word; }
.compare-arrow { display: grid; place-items: center; color: var(--muted); }
.diff-move { display: flex; align-items: center; gap: 10px; padding: 10px 16px; font-family: ui-monospace, monospace; font-size: 12.5px; }
.diff-move code { background: rgba(217,153,6,0.12); color: #8a5b00; padding: 2px 8px; border-radius: 6px; }
.move-arrow { color: var(--muted); }
</style>
