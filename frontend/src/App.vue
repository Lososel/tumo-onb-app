<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="mx-auto flex min-h-dvh w-full max-w-md flex-col px-4 pb-[max(1.5rem,env(safe-area-inset-bottom))]">
    <header class="flex items-center justify-between py-4">
      <RouterLink to="/" class="flex items-center gap-2" aria-label="TUMO Astana home">
        <span class="grid h-9 w-9 place-items-center rounded-xl bg-brand-500 text-lg font-bold text-white">T</span>
        <span class="text-base font-semibold tracking-tight text-slate-900">TUMO Astana</span>
      </RouterLink>
      <RouterLink
        to="/guide"
        class="rounded-full px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100"
        active-class="bg-slate-100 text-slate-900"
      >
        Guide
      </RouterLink>
    </header>
    <main class="flex flex-1 flex-col">
      <RouterView />
    </main>
  </div>
</template>
