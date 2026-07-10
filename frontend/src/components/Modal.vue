<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="show" class="modal-backdrop" @click.self="onBackdropClick" @keydown.esc="onClose">
        <div class="modal-dialog" role="dialog" :aria-modal="show">
          <header class="modal-header">
            <h3 class="modal-title">{{ title }}</h3>
            <button type="button" class="modal-close" @click="onClose" aria-label="关闭">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M12 4L4 12M4 4l8 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
            </button>
          </header>
          <div class="modal-body">
            <slot />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
defineProps<{
  show: boolean
  title: string
}>()

const emit = defineEmits<{
  close: []
}>()

function onClose() {
  emit('close')
}

function onBackdropClick() {
  emit('close')
}
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: grid;
  place-items: center;
  background: rgba(15, 23, 42, 0.35);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}

.modal-dialog {
  width: min(720px, 92vw);
  max-height: 82vh;
  border-radius: 20px;
  background: var(--surface-solid);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.18), 0 0 0 1px rgba(17, 24, 39, 0.06);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px 14px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}

.modal-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
}

.modal-close {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  border: none;
  background: rgba(17, 24, 39, 0.05);
  color: var(--muted);
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: background 0.15s ease, color 0.15s ease;
}

.modal-close:hover {
  background: rgba(217, 45, 32, 0.1);
  color: var(--danger);
}

.modal-body {
  padding: 20px 22px 22px;
  overflow-y: auto;
  flex: 1;
}

/* ---- transition ---- */
.modal-enter-active { transition: all 0.28s cubic-bezier(0.16, 1, 0.3, 1); }
.modal-leave-active { transition: all 0.2s ease-in; }
.modal-enter-from .modal-dialog,
.modal-leave-to .modal-dialog {
  opacity: 0;
  transform: translateY(16px) scale(0.97);
}
.modal-enter-from .modal-backdrop,
.modal-leave-to .modal-backdrop {
  opacity: 0;
}
</style>
