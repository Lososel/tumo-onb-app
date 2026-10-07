<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import ScheduleCard from '../components/ScheduleCard.vue'
import { lookupResult, setLookupResult } from '../session'

const router = useRouter()
const result = computed(() => lookupResult.value)

if (!result.value) router.replace({ name: 'home' })

function searchAgain() {
  setLookupResult(null)
  router.push({ name: 'home' })
}

function workshopDetails(teacher: string | null, room: string | null) {
  return [teacher && `👩‍🏫 ${teacher}`, room && `📍 ${room}`].filter(Boolean) as string[]
}
</script>

<template>
  <section v-if="result" class="flex flex-1 flex-col py-2">
    <!-- Found -->
    <template v-if="result.status === 'ok'">
      <div v-for="(student, i) in result.students" :key="i" class="space-y-4" :class="{ 'mt-10': i > 0 }">
        <div>
          <h1 class="text-2xl font-bold tracking-tight text-slate-900">Welcome, {{ student.first_name }}! 👋</h1>
          <p class="mt-1 text-slate-600">Here's your TUMO schedule.</p>
        </div>

        <ScheduleCard
          v-if="student.self_study"
          icon="💻"
          label="Self-study"
          title="Self-learning sessions"
          :days="student.self_study.days"
          :time="student.self_study.time"
          accent="sky"
        />
        <ScheduleCard
          v-for="w in student.workshops"
          :key="w.name"
          icon="🎨"
          label="Workshop"
          :title="w.name"
          :details="workshopDetails(w.teacher, w.room)"
          :days="w.days"
          :time="w.time"
        />
        <p
          v-if="!student.self_study && !student.workshops.length"
          class="rounded-2xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-600"
        >
          Your schedule isn't set yet. Check back soon or ask a TUMO coach. 🙂
        </p>

        <div class="grid gap-3 pt-2">
          <a
            v-if="student.links.whatsapp"
            :href="student.links.whatsapp"
            target="_blank"
            rel="noopener noreferrer"
            class="flex items-center justify-center gap-2 rounded-xl bg-[#25D366] px-4 py-3.5 font-semibold text-white shadow-sm transition hover:brightness-95 active:scale-[0.99]"
          >
            💬 Join WhatsApp Group
          </a>
          <RouterLink
            to="/guide"
            class="flex items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-3.5 font-semibold text-slate-800 transition hover:bg-slate-50 active:scale-[0.99]"
          >
            📚 How TUMO works
          </RouterLink>
        </div>
      </div>
    </template>

    <!-- Not found / inactive -->
    <div v-else class="flex flex-1 flex-col items-center justify-center text-center">
      <div class="text-5xl" aria-hidden="true">{{ result.status === 'inactive' ? '⏸️' : '🔍' }}</div>
      <h1 class="mt-4 text-xl font-bold text-slate-900">
        {{ result.status === 'inactive' ? 'Your enrollment is paused' : "Hmm, we couldn't find you" }}
      </h1>
      <p class="mt-2 max-w-xs text-slate-600">{{ result.message }}</p>
      <RouterLink
        to="/guide"
        class="mt-6 text-sm font-medium text-brand-600 hover:underline"
      >
        Meanwhile, learn how TUMO works →
      </RouterLink>
    </div>

    <div class="mt-auto pt-8 text-center">
      <button type="button" class="text-sm font-medium text-slate-500 hover:text-slate-800" @click="searchAgain">
        {{ result.status === 'ok' ? 'Not you? Search again' : '← Try another name' }}
      </button>
    </div>
  </section>
</template>
