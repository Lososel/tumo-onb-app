<script setup lang="ts">
import { computed } from 'vue'
import type { Learner } from '../api'
import { localized, locale, t } from '../i18n'

const props = defineProps<{ learner: Learner }>()

const BADGE: Record<string, string> = {
  coach_unchanged: 'bg-emerald-50 text-emerald-700',
  unchanged: 'bg-emerald-50 text-emerald-700',
  schedule_changed: 'bg-amber-50 text-amber-700',
  coach_changed: 'bg-sky-50 text-sky-700',
  pending: 'bg-slate-100 text-slate-600',
}

const badge = computed(() => {
  const { status_code: code, status } = props.learner
  if (code) return { text: t.value.status[code], cls: BADGE[code] }
  return status ? { text: status, cls: 'bg-slate-100 text-slate-600' } : null
})

const stage = computed(() => {
  const { stage_code: code, stage } = props.learner
  return code ? t.value.stage[code] : stage
})

const statusNote = computed(() => {
  const code = props.learner.status_code
  return code ? t.value.statusNote[code] : null
})

const customNote = computed(() => {
  const { note, note_kk } = props.learner
  return locale.value === 'kk' && note_kk ? note_kk : note
})

const fields = computed(() => [
  { label: t.value.card.schedule, value: localized(props.learner.schedule, props.learner.schedule_kk) },
  {
    label: t.value.card.selfStudyDay,
    value: localized(props.learner.self_study_day, props.learner.self_study_day_kk),
  },
  { label: t.value.card.coach, value: props.learner.coach },
  { label: t.value.card.coachEmail, value: props.learner.coach_email, email: true },
  { label: t.value.card.stage, value: stage.value },
])
</script>

<template>
  <article class="rounded-3xl border-2 border-ink bg-white p-5 sm:p-8">
    <div class="flex flex-col-reverse items-start gap-3 sm:flex-row sm:items-start sm:justify-between">
      <h3 class="font-display text-xl leading-snug font-black text-ink sm:text-2xl">{{ learner.full_name }}</h3>
      <span
        v-if="badge"
        class="shrink-0 rounded-full px-3.5 py-1.5 text-xs font-extrabold tracking-wide uppercase"
        :class="badge.cls"
      >
        {{ badge.text }}
      </span>
    </div>

    <dl class="mt-5 grid gap-x-8 gap-y-5 sm:mt-6 sm:grid-cols-2">
      <div v-for="f in fields" :key="f.label" class="min-w-0">
        <dt class="text-xs font-bold tracking-wider text-slate-500 uppercase">{{ f.label }}</dt>
        <dd class="mt-1 text-lg font-semibold break-words text-ink">
          <a
            v-if="f.email && f.value"
            :href="`mailto:${f.value}`"
            class="font-medium text-brand-500 hover:underline"
          >{{ f.value }}</a>
          <template v-else>{{ f.value || t.card.notSet }}</template>
        </dd>
      </div>
    </dl>

    <p v-if="statusNote" class="mt-6 rounded-2xl bg-brand-50 px-5 py-3.5 text-[0.95rem] text-slate-700">
      {{ statusNote }}
    </p>
    <p v-if="customNote" class="mt-3 rounded-2xl bg-sky-50 px-5 py-3.5 text-[0.95rem] text-slate-700">
      {{ customNote }}
    </p>
  </article>
</template>
