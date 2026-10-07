<script setup lang="ts">
import { computed, ref } from 'vue'
import { errorKind, lookupSchedule, type ErrorKind, type LookupResponse } from '../api'
import { format, t } from '../i18n'
import ScheduleCard from './ScheduleCard.vue'
import SectionTitle from './SectionTitle.vue'

const query = defineModel<string>({ default: '' })

const loading = ref(false)
const result = ref<LookupResponse | null>(null)
const error = ref<ErrorKind | 'empty' | null>(null)

async function search() {
  if (loading.value) return
  if (!query.value.trim()) {
    error.value = 'empty'
    result.value = null
    return
  }
  loading.value = true
  error.value = null
  try {
    result.value = await lookupSchedule(query.value)
  } catch (err) {
    result.value = null
    error.value = errorKind(err)
  } finally {
    loading.value = false
  }
}

const message = computed(() => {
  if (error.value) return t.value.search[error.value]
  switch (result.value?.status) {
    case 'not_found':
      return t.value.search.notFound
    case 'inactive':
      return t.value.search.inactive
    case 'need_full_name':
      return t.value.search.needFullName
    case 'too_many':
      return t.value.search.tooMany
    case 'unavailable':
      return t.value.search.unavailable
    default:
      return null
  }
})

const updatedAt = computed(() => {
  const iso = result.value?.data_updated_at
  if (!iso || result.value?.status !== 'ok') return null
  // Fixed dd.mm.yyyy, hh:mm — not every browser ships Kazakh locale data for Intl.
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  const date = `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}, ${pad(d.getHours())}:${pad(d.getMinutes())}`
  return format(t.value.search.updatedAt, { date })
})
</script>

<template>
  <section aria-labelledby="search-title">
    <SectionTitle id="search-title">{{ t.search.title }}</SectionTitle>

    <div class="mt-6 space-y-4 text-base leading-relaxed text-slate-700 sm:mt-8 sm:text-lg">
      <p v-for="(p, i) in t.search.intro" :key="i">{{ p }}</p>
    </div>

    <form class="mt-8 flex gap-2 sm:mt-10 sm:gap-3" role="search" @submit.prevent="search">
      <label class="sr-only" for="learner-name">{{ t.search.placeholder }}</label>
      <input
        id="learner-name"
        v-model="query"
        type="search"
        enterkeyhint="search"
        autocomplete="off"
        autocapitalize="words"
        maxlength="120"
        :placeholder="t.search.placeholder"
        class="min-w-0 flex-1 rounded-full border-2 border-brand-400 bg-white px-5 py-3.5 text-base text-ink shadow-[0_0_0_4px_var(--color-brand-100)] outline-none placeholder:text-slate-400 focus:border-brand-500 sm:px-7 sm:py-5 sm:text-lg"
      />
      <button
        type="submit"
        :disabled="loading"
        class="shrink-0 rounded-full bg-ink px-5 font-bold text-white transition hover:bg-black active:scale-[0.98] disabled:opacity-60 sm:px-9 sm:text-lg"
      >
        {{ loading ? t.search.searching : t.search.button }}
      </button>
    </form>

    <div aria-live="polite" class="mt-8 space-y-5">
      <p
        v-if="message"
        class="rounded-2xl border-2 border-dashed border-brand-200 bg-brand-50 px-5 py-4 text-slate-700"
        role="status"
      >
        {{ message }}
      </p>
      <template v-if="result?.status === 'ok'">
        <ScheduleCard v-for="(l, i) in result.results" :key="i" :learner="l" />
        <p v-if="updatedAt" class="text-center text-sm text-slate-400">{{ updatedAt }}</p>
      </template>
    </div>
  </section>
</template>
