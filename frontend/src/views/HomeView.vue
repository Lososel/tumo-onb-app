<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { errorMessage, lookupStudent } from '../api'
import { setLookupResult } from '../session'

const router = useRouter()
const firstName = ref('')
const lastName = ref('')
const loading = ref(false)
const error = ref('')

const canSubmit = computed(() => firstName.value.trim() && lastName.value.trim() && !loading.value)

async function submit() {
  if (!canSubmit.value) return
  loading.value = true
  error.value = ''
  try {
    setLookupResult(await lookupStudent(firstName.value, lastName.value))
    await router.push({ name: 'dashboard' })
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="flex flex-1 flex-col justify-center py-6">
    <div class="text-center">
      <div class="text-5xl" aria-hidden="true">👋</div>
      <h1 class="mt-4 text-2xl font-bold tracking-tight text-slate-900">Hi! Let's find your schedule</h1>
      <p class="mt-2 text-slate-600">Enter your name exactly as you registered at TUMO.</p>
    </div>

    <form class="mt-8 space-y-4" novalidate @submit.prevent="submit">
      <label class="block">
        <span class="mb-1.5 block text-sm font-medium text-slate-700">First name</span>
        <input
          v-model="firstName"
          type="text"
          name="given-name"
          autocomplete="given-name"
          autocapitalize="words"
          maxlength="60"
          placeholder="e.g. Aruzhan"
          class="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-base text-slate-900 outline-none placeholder:text-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-100"
        />
      </label>
      <label class="block">
        <span class="mb-1.5 block text-sm font-medium text-slate-700">Last name</span>
        <input
          v-model="lastName"
          type="text"
          name="family-name"
          autocomplete="family-name"
          autocapitalize="words"
          maxlength="60"
          placeholder="e.g. Smagulova"
          class="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-base text-slate-900 outline-none placeholder:text-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-100"
        />
      </label>

      <p v-if="error" role="alert" class="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>

      <button
        type="submit"
        :disabled="!canSubmit"
        class="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-500 px-4 py-3.5 text-base font-semibold text-white shadow-sm transition hover:bg-brand-600 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-50"
      >
        <svg v-if="loading" class="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="opacity-25" />
          <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" stroke-width="4" stroke-linecap="round" />
        </svg>
        {{ loading ? 'Searching…' : 'Show my schedule' }}
      </button>
    </form>

    <RouterLink to="/guide" class="mt-6 text-center text-sm font-medium text-brand-600 hover:underline">
      New to TUMO? See how it works →
    </RouterLink>
  </section>
</template>
