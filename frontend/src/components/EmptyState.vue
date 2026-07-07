<template>
  <section class="card empty-state">
    <p class="eyebrow">{{ eyebrow }}</p>
    <h2>{{ title }}</h2>
    <p>{{ description }}</p>
    <RouterLink v-if="actionTo" :to="actionTo" class="button primary">{{ actionLabel }}</RouterLink>
  </section>
</template>

<script setup lang="ts">
defineProps<{ eyebrow: string; title: string; description: string; actionLabel?: string; actionTo?: string }>()
</script>
