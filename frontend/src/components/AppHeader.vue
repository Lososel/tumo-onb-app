<script setup lang="ts">
import { locale, setLocale, t, type Locale } from '../i18n'

const locales: Locale[] = ['ru', 'kk']
</script>

<template>
  <header class="bg-black">
    <div class="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:h-[5.5rem] sm:px-8">
      <a href="/" class="flex items-baseline gap-1.5 text-white" aria-label="TUMO Astana">
        <span class="font-display text-2xl font-black tracking-tight sm:text-3xl" style="-webkit-text-stroke: 0.5px #fff">
          TUMO
        </span>
        <span class="font-display text-base font-black lowercase sm:text-lg">astana</span>
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
  </header>
</template>
