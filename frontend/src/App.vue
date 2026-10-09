<script setup lang="ts">
import { ref } from 'vue'
import AppHeader from './components/AppHeader.vue'
import FaqSection from './components/FaqSection.vue'
import ScheduleSearch from './components/ScheduleSearch.vue'
import StudentChecklist from './components/StudentChecklist.vue'
import SupportCard from './components/SupportCard.vue'
import { t } from './i18n'

const query = ref('')
</script>

<template>
  <AppHeader />
  <main class="mx-auto max-w-4xl space-y-16 px-4 py-10 sm:space-y-20 sm:px-6 sm:py-16">
    <ScheduleSearch v-model="query" />
    <StudentChecklist />
    <FaqSection />
    <SupportCard :learner-name="query" />
  </main>
  <footer class="px-4 pt-4 pb-10 text-center text-sm text-slate-500 sm:pb-14">{{ t.footer }}</footer>
</template>
