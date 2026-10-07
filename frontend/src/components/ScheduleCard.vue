<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import { PENDING, type Learner } from '../api'
import { localized, t } from '../i18n'

const props = defineProps<{ learner: Learner }>()

const BADGE: Record<string, string> = {
  active_schedule: 'bg-emerald-50 text-emerald-700',
  waitlist: 'bg-amber-50 text-amber-700',
  schedule_pending: 'bg-slate-100 text-slate-600',
  schedule_changed: 'bg-amber-50 text-amber-700',
  coach_changed: 'bg-sky-50 text-sky-700',
}

const badge = computed(() => {
  const { status_code: code, status } = props.learner
  if (code !== 'other') return { text: t.value.status[code], cls: BADGE[code] }
  return status ? { text: status, cls: 'bg-slate-100 text-slate-600' } : null
})

const statusNote = computed(() => {
  const code = props.learner.status_code
  return code !== 'other' ? t.value.statusNote[code] : ''
})

// The API's "Уточняется" placeholder becomes null here so it renders as the localized t.card.notSet.
const known = (v: string | null) => (v === PENDING ? null : v)

const fields = computed(() => [
  { label: t.value.card.schedule, value: localized(props.learner.schedule) },
  { label: t.value.card.coach, value: props.learner.coach_name },
  { label: t.value.card.room, value: known(props.learner.room) },
  { label: t.value.card.email, value: known(props.learner.default_email) },
])

// Temporary password: masked until the learner asks to see it; re-masked for every new result.
const passwordLabelId = useId()
const revealed = ref(false)
const copied = ref(false)
watch(
  () => props.learner,
  () => {
    revealed.value = false
    copied.value = false
  },
)

async function copyPassword() {
  if (!props.learner.temp_password) return
  try {
    await navigator.clipboard.writeText(props.learner.temp_password)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    revealed.value = true // clipboard blocked: show it so it can be copied by hand
  }
}
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
        <dd class="mt-1 text-lg font-semibold break-words text-ink">{{ f.value || t.card.notSet }}</dd>
      </div>
    </dl>

    <div v-if="learner.temp_password" class="mt-6 rounded-2xl border border-brand-200 bg-brand-50 p-4 sm:p-5">
      <p :id="passwordLabelId" class="text-xs font-bold tracking-wider text-slate-500 uppercase">
        {{ t.card.password }}
      </p>
      <div class="mt-2 flex flex-wrap items-center gap-2 sm:gap-3">
        <code
          :aria-labelledby="passwordLabelId"
          class="w-full min-w-0 overflow-x-auto rounded-xl bg-white px-4 py-2.5 font-mono text-lg tracking-wider whitespace-nowrap text-ink sm:w-auto sm:flex-1"
        >{{ revealed ? learner.temp_password : '••••••••' }}</code>
        <button
          type="button"
          :aria-pressed="revealed"
          class="rounded-full bg-ink px-4 py-2.5 text-sm font-bold text-white transition hover:bg-black"
          @click="revealed = !revealed"
        >
          {{ revealed ? t.card.hide : t.card.show }}
        </button>
        <button
          type="button"
          class="rounded-full border-2 border-ink px-4 py-2 text-sm font-bold text-ink transition hover:bg-ink hover:text-white"
          @click="copyPassword"
        >
          {{ copied ? t.card.copied : t.card.copy }}
        </button>
      </div>
      <p class="mt-3 text-sm text-slate-600">{{ t.card.passwordHint }}</p>
    </div>

    <p v-if="statusNote" class="mt-6 rounded-2xl bg-sky-50 px-5 py-3.5 text-[0.95rem] text-slate-700">
      {{ statusNote }}
    </p>
  </article>
</template>
