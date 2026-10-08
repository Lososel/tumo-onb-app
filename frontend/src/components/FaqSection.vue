<script setup lang="ts">
import { t } from '../i18n'
import ComingSoonBadge from './ComingSoonBadge.vue'
import SectionTitle from './SectionTitle.vue'
</script>

<template>
  <section aria-labelledby="faq-title">
    <SectionTitle id="faq-title">{{ t.faq.title }}</SectionTitle>
    <div class="mt-6 sm:mt-8">
      <details v-for="(item, i) in t.faq.items" :key="i" class="group border-b border-slate-200">
        <summary
          class="flex cursor-pointer list-none items-center justify-between gap-4 px-1 py-5 text-base font-bold text-ink sm:py-7 sm:text-lg [&::-webkit-details-marker]:hidden"
        >
          {{ item.q }}
          <span
            class="shrink-0 text-2xl leading-none font-bold text-brand-500 transition-transform group-open:rotate-45"
            aria-hidden="true"
          >+</span>
        </summary>
        <div class="px-1 pb-6 leading-relaxed text-slate-600">
          <p class="whitespace-pre-line">{{ item.a }}</p>
          <ul v-if="'upcoming' in item && item.upcoming" class="mt-3 space-y-2">
            <li v-for="(feature, j) in item.upcoming" :key="j" class="flex flex-wrap items-center gap-2">
              {{ feature }}
              <ComingSoonBadge />
            </li>
          </ul>
        </div>
      </details>
    </div>
  </section>
</template>
