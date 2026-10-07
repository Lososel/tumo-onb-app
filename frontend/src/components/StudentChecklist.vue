<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { format, t } from '../i18n'
import SectionTitle from './SectionTitle.vue'
import ChecklistIcon from './ChecklistIcon.vue'

// Ticks are a per-device convenience only: kept in this browser, never sent anywhere.
const KEY = 'tumo.checklist'

function restore(): boolean[] {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || '[]')
    return Array.isArray(saved) ? saved.map(Boolean) : []
  } catch {
    return []
  }
}

const done = ref<boolean[]>(restore())
watch(
  done,
  (value) => {
    try {
      localStorage.setItem(KEY, JSON.stringify(value))
    } catch {
      /* storage unavailable (private mode): ticks just aren't remembered */
    }
  },
  { deep: true },
)

const steps = computed(() => t.value.checklist.steps)
const doneCount = computed(() => steps.value.filter((_, i) => done.value[i]).length)

function toggle(i: number) {
  const next = [...done.value]
  next[i] = !next[i]
  done.value = next
}

// Minimal inline markup in the locale text: **bold** and `code`. Rendered as tokens, not HTML.
type Token = { text: string; kind: 'text' | 'bold' | 'code' }
function tokens(line: string): Token[] {
  return line
    .split(/(\*\*[^*]+\*\*|`[^`]+`)/)
    .filter(Boolean)
    .map((part) =>
      part.startsWith('**')
        ? { text: part.slice(2, -2), kind: 'bold' }
        : part.startsWith('`')
          ? { text: part.slice(1, -1), kind: 'code' }
          : { text: part, kind: 'text' },
    )
}
</script>

<template>
  <section id="checklist" aria-labelledby="checklist-title" class="scroll-mt-6">
    <SectionTitle id="checklist-title">
      <ChecklistIcon name="clipboard" class="-mt-1 mr-1 inline-block size-[0.9em] align-middle" />{{ t.checklist.title }}
    </SectionTitle>

    <p class="mt-6 text-base leading-relaxed text-slate-700 sm:mt-8 sm:text-lg">{{ t.checklist.intro }}</p>

    <p class="mt-4 text-sm font-bold text-brand-600" aria-live="polite">
      {{ format(t.checklist.progress, { done: String(doneCount), total: String(steps.length) }) }}
    </p>

    <ol class="mt-4 space-y-4">
      <li
        v-for="(step, i) in steps"
        :key="i"
        class="rounded-3xl border-2 p-5 transition sm:p-6"
        :class="done[i] ? 'border-emerald-300 bg-emerald-50/50' : 'border-ink bg-white'"
      >
        <div class="flex items-start gap-3 sm:gap-4">
          <span
            class="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-brand-50 text-brand-500"
            aria-hidden="true"
          ><ChecklistIcon :name="step.icon" class="size-6" /></span>
          <h3 class="min-w-0 flex-1 self-center font-display text-lg leading-snug font-black text-ink sm:text-xl">
            <span class="text-brand-500">{{ i + 1 }}.</span> {{ step.title }}
          </h3>
          <button
            type="button"
            role="checkbox"
            :aria-checked="!!done[i]"
            :aria-label="`${t.checklist.markDone}: ${step.title}`"
            class="grid h-9 w-9 shrink-0 place-items-center rounded-full border-2 transition"
            :class="done[i] ? 'border-emerald-500 bg-emerald-500 text-white' : 'border-slate-300 text-transparent hover:border-brand-400'"
            @click="toggle(i)"
          >
            <svg viewBox="0 0 20 20" fill="currentColor" class="h-5 w-5" aria-hidden="true">
              <path fill-rule="evenodd" d="M16.7 5.3a1 1 0 0 1 0 1.4l-7.5 7.5a1 1 0 0 1-1.4 0L3.3 9.7a1 1 0 1 1 1.4-1.4l3.8 3.8 6.8-6.8a1 1 0 0 1 1.4 0z" clip-rule="evenodd" />
            </svg>
          </button>
        </div>

        <ul class="mt-4 space-y-2.5 pl-1 sm:pl-[3.75rem]">
          <li v-for="(line, j) in step.items" :key="j" class="flex gap-2.5 leading-relaxed text-slate-700">
            <span class="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-400" aria-hidden="true" />
            <span>
              <template v-for="(tok, k) in tokens(line)" :key="k">
                <strong v-if="tok.kind === 'bold'" class="font-bold text-ink">{{ tok.text }}</strong>
                <code v-else-if="tok.kind === 'code'" class="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.9em] text-ink">{{ tok.text }}</code>
                <template v-else>{{ tok.text }}</template>
              </template>
            </span>
          </li>
        </ul>
      </li>
    </ol>
  </section>
</template>
