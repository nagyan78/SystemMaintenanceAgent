<script setup lang="ts">
import type { Component } from "vue";

defineProps<{
  label: string;
  value: string | number;
  tone?: "blue" | "red" | "green" | "muted";
  icon: Component;
  suffix?: string;
}>();
</script>

<template>
  <section class="metric-card" :class="`metric-card--${tone ?? 'blue'}`">
    <div class="metric-card__icon">
      <component :is="icon" :size="30" :stroke-width="1.8" />
    </div>
    <div>
      <p>{{ label }}</p>
      <strong>{{ value }}<span v-if="suffix">{{ suffix }}</span></strong>
    </div>
  </section>
</template>
