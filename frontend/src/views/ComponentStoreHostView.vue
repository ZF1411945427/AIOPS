<template>
  <div class="store-host">
    <ComponentStoreView />
  </div>
</template>

<script setup>
import ComponentStoreView from '@/views/ComponentStoreView.vue'
</script>

<style scoped>
.store-host { padding: 0; }
.store-host :deep(.store-page) { padding: 12px; }
</style>
