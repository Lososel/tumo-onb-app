<script setup lang="ts">
import { t } from '../i18n'
</script>

<template>
  <!-- The project's one label for features that aren't available yet. -->
  <span
    class="inline-flex shrink-0 items-center rounded-full bg-brand-100 px-2.5 py-0.5 text-xs font-bold whitespace-nowrap text-brand-600"
  >{{ t.coming_soon }}</span>
</template>
