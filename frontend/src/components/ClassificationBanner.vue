<script setup lang="ts">
defineProps<{ marking: string }>()
</script>
<template>
  <div class="rt-classification w-full py-1.5 text-center bg-amber-500/90 text-zinc-950">
    {{ marking }}
  </div>
</template>
