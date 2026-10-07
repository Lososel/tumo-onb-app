<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

const phases = [
  {
    n: '01',
    icon: '💻',
    title: 'Self-study',
    text: 'Learn at your own pace with interactive activities on the TUMO Path. Pick topics you love — animation, programming, music, design and more — while coaches are around to help.',
  },
  {
    n: '02',
    icon: '🎨',
    title: 'Workshop',
    text: 'Join small-group workshops led by a TUMO specialist. Each workshop runs for several weeks and helps you build real skills by making something together.',
  },
  {
    n: '03',
    icon: '🚀',
    title: 'Projects',
    text: 'Put your skills to work in project labs. Team up with others and professionals to create real projects you can be proud of and add to your portfolio.',
  },
  {
    n: '04',
    icon: '📈',
    title: 'Progress',
    text: 'Every activity, workshop and project counts. Track your growth, level up through focus areas, and shape your own learning path at TUMO.',
  },
]

function back() {
  if (window.history.state?.back) router.back()
  else router.push({ name: 'home' })
}
</script>

<template>
  <section class="py-2">
    <button type="button" class="mb-4 text-sm font-medium text-slate-500 hover:text-slate-800" @click="back">
      ← Back
    </button>
    <h1 class="text-2xl font-bold tracking-tight text-slate-900">How TUMO works 📚</h1>
    <p class="mt-1 text-slate-600">Your learning journey in four steps.</p>

    <ol class="relative mt-6 space-y-4">
      <li v-for="p in phases" :key="p.n" class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div class="flex items-center gap-3">
          <span class="text-sm font-bold text-brand-500 tabular-nums">{{ p.n }}</span>
          <span class="text-xl" aria-hidden="true">{{ p.icon }}</span>
          <h2 class="text-lg font-semibold text-slate-900">{{ p.title }}</h2>
        </div>
        <p class="mt-2 text-sm leading-relaxed text-slate-600">{{ p.text }}</p>
      </li>
    </ol>
  </section>
</template>
