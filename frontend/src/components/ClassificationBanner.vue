<script setup lang="ts">
defineProps<{ marking: string }>()
</script>
<template>
  <div class="rt-classification w-full text-center text-xs font-semibold py-1 bg-base-300">
    {{ marking }}
  </div>
</template>
