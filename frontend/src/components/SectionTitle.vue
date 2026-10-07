<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

// A wrapped heading keeps its box as wide as the space it was given, which squeezes the
// decorative side lines to a stub. Shrink the box to its widest rendered line instead.
const row = ref<HTMLElement>()
const heading = ref<HTMLElement>()
let resize: ResizeObserver | undefined
let mutation: MutationObserver | undefined

function fit() {
  const el = heading.value
  if (!el) return
  el.style.width = '' // lay out at full available width first
  const range = document.createRange()
  range.selectNodeContents(el)
  const lines = new Map<number, { left: number; right: number }>()
  for (const r of range.getClientRects()) {
    if (!r.width) continue
    const key = Math.round(r.top)
    const line = lines.get(key) ?? { left: r.left, right: r.right }
    lines.set(key, { left: Math.min(line.left, r.left), right: Math.max(line.right, r.right) })
  }
  if (lines.size < 2) return
  const widest = Math.max(...[...lines.values()].map((l) => l.right - l.left))
  el.style.width = `${Math.ceil(widest) + 2}px`
}

onMounted(() => {
  fit()
  document.fonts?.ready.then(fit)
  resize = new ResizeObserver(fit) // the row, not the heading: its width doesn't depend on ours
  if (row.value) resize.observe(row.value)
  mutation = new MutationObserver(fit) // language switch changes the text
  if (heading.value) mutation.observe(heading.value, { characterData: true, childList: true, subtree: true })
})

onBeforeUnmount(() => {
  resize?.disconnect()
  mutation?.disconnect()
})
</script>

<template>
  <div ref="row" class="flex items-center gap-3 sm:gap-5">
    <span class="h-0.5 min-w-6 flex-1 bg-brand-400" aria-hidden="true" />
    <h2
      ref="heading"
      class="text-center text-balance font-display text-2xl leading-tight font-black text-brand-500 sm:text-[2.5rem]"
    >
      <slot />
    </h2>
    <span class="h-0.5 min-w-6 flex-1 bg-brand-400" aria-hidden="true" />
  </div>
</template>
