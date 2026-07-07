<template>
  <section class="card">
    <div class="card-head">
      <div>
        <p class="eyebrow">{{ phase }}</p>
        <h2>{{ label }}</h2>
      </div>
      <span class="badge" :data-tone="tone">{{ status }}</span>
    </div>
    <div class="timeline">
      <div v-for="step in steps" :key="step.key" class="timeline-step" :data-state="step.state">
        <div class="timeline-dot"></div>
        <div>
          <div class="timeline-label">{{ step.label }}</div>
          <div class="timeline-meta">{{ step.phase }}</div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{ phase: string; label: string; status: string; tone?: string; steps: Array<{ key: string; label: string; phase: string; state: string }> }>()
</script>
