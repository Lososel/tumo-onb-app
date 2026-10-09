<script setup lang="ts">
import { computed } from 'vue'
import { contacts, whatsappLink } from '../config'
import { t } from '../i18n'

const props = defineProps<{ learnerName?: string }>()

// Pre-fills the WhatsApp message with the name typed in the search box (the user sends it themselves).
const waHref = computed(() => whatsappLink(t.value.support.whatsappMessage + (props.learnerName?.trim() ?? '')))

const rows = computed(() => [
  { label: t.value.support.email, text: contacts.email, href: `mailto:${contacts.email}` },
  { label: t.value.support.whatsapp, text: contacts.whatsappDisplay, href: whatsappLink() },
  { label: t.value.support.instagram, text: `@${contacts.instagram}`, href: `https://instagram.com/${contacts.instagram}` },
  { label: t.value.support.website, text: contacts.website, href: `https://${contacts.website}` },
])
</script>

<template>
  <section class="rounded-3xl bg-ink p-6 text-white sm:p-8" aria-labelledby="support-title">
    <h2 id="support-title" class="font-display text-xl leading-snug font-black sm:text-2xl">{{ t.support.title }}</h2>
    <div class="mt-3 space-y-1 leading-relaxed text-white/80 sm:text-lg">
      <p v-for="(p, i) in t.support.text" :key="i">{{ p }}</p>
    </div>

    <a
      :href="waHref"
      target="_blank"
      rel="noopener noreferrer"
      class="mt-6 inline-flex rounded-full border-2 border-brand-400 px-7 py-3.5 font-bold text-brand-400 transition hover:bg-brand-400 hover:text-ink"
    >
      {{ t.support.button }}
    </a>

    <hr class="my-6 border-white/15" />

    <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2.5 sm:text-lg">
      <template v-for="r in rows" :key="r.label">
        <dt class="text-white/60">{{ r.label }}</dt>
        <dd class="min-w-0 break-words">
          <a :href="r.href" target="_blank" rel="noopener noreferrer" class="text-brand-400 hover:underline">{{ r.text }}</a>
        </dd>
      </template>
      <dt class="col-span-2 mt-1 text-white/60">{{ t.support.address }}</dt>
      <dd class="col-span-2 leading-relaxed text-white/85">{{ t.support.addressValue }}</dd>
    </dl>
  </section>
</template>
