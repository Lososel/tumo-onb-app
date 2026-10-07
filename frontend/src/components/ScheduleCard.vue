<script setup lang="ts">
defineProps<{
  icon: string
  label: string
  title: string
  days: string
  time: string
  details?: string[]
  accent?: 'brand' | 'sky'
}>()
</script>

<template>
  <article class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
    <div class="flex items-start gap-3">
      <div
        class="grid h-11 w-11 shrink-0 place-items-center rounded-xl text-xl"
        :class="accent === 'sky' ? 'bg-sky-100' : 'bg-brand-100'"
        aria-hidden="true"
      >
        {{ icon }}
      </div>
      <div class="min-w-0 flex-1">
        <p
          class="text-xs font-semibold tracking-wide uppercase"
          :class="accent === 'sky' ? 'text-sky-700' : 'text-brand-700'"
        >
          {{ label }}
        </p>
        <h3 class="mt-0.5 text-base font-semibold text-slate-900">{{ title }}</h3>
        <p v-if="details?.length" class="mt-0.5 text-sm text-slate-500">{{ details.join(' · ') }}</p>
      </div>
    </div>
    <dl class="mt-4 grid grid-cols-2 gap-2 text-sm">
      <div class="rounded-xl bg-slate-50 px-3 py-2">
        <dt class="text-xs text-slate-500">📅 Days</dt>
        <dd class="font-medium text-slate-900">{{ days || '—' }}</dd>
      </div>
      <div class="rounded-xl bg-slate-50 px-3 py-2">
        <dt class="text-xs text-slate-500">🕒 Time</dt>
        <dd class="font-medium text-slate-900">{{ time || '—' }}</dd>
      </div>
    </dl>
  </article>
</template>
