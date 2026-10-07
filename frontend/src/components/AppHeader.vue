<script setup lang="ts">
import { locale, setLocale, t, type Locale } from '../i18n'

const locales: Locale[] = ['ru', 'kk']
</script>

<template>
  <header class="bg-black">
    <div class="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:h-[5.5rem] sm:px-8">
      <a href="/" class="block shrink-0" aria-label="TUMO Astana">
        <!-- White logo on transparent background (600×139), sized by height for the black header. -->
        <img src="/logo.png" alt="TUMO Astana" width="600" height="139" class="h-7 w-auto sm:h-10" />
      </a>

      <div class="flex items-center gap-2 sm:gap-4">
        <!-- Jump to the onboarding checklist; icon only on phones to keep the header compact. -->
        <a
          href="#checklist"
          class="flex items-center gap-1.5 rounded-full px-2.5 py-1.5 text-sm font-bold text-white transition hover:bg-white/10 sm:px-3"
          :aria-label="t.checklist.nav"
        >
          <span aria-hidden="true">📋</span>
          <span class="hidden sm:inline">{{ t.checklist.nav }}</span>
        </a>
        <div
          role="group"
          :aria-label="t.lang.label"
          class="flex rounded-full border-2 border-white bg-black p-0.5 text-xs font-bold sm:text-sm"
        >
          <button
            v-for="l in locales"
            :key="l"
            type="button"
            :aria-pressed="locale === l"
            class="rounded-full px-3.5 py-1.5 transition sm:px-4 sm:py-2"
            :class="locale === l ? 'bg-white text-black' : 'text-white hover:bg-white/10'"
            @click="setLocale(l)"
          >
            {{ t.lang[l] }}
          </button>
        </div>
      </div>
    </div>
  </header>
</template>
