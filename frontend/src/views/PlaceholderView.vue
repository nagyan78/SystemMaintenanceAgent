<script setup lang="ts">
defineProps<{
  eyebrow: string;
  title: string;
  status: string;
}>();
</script>

<template>
  <section class="panel placeholder-page">
    <p class="eyebrow">{{ eyebrow }}</p>
    <h2>{{ title }}</h2>
    <strong>{{ status }}</strong>
  </section>
</template>
