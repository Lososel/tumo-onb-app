<template>
  <div class="flex items-center gap-3 sm:gap-5">
    <span class="h-0.5 min-w-6 flex-1 bg-brand-400" aria-hidden="true" />
    <h2 class="text-center font-display text-2xl leading-tight font-black text-brand-500 sm:text-[2.5rem]">
      <slot />
    </h2>
    <span class="h-0.5 min-w-6 flex-1 bg-brand-400" aria-hidden="true" />
  </div>
</template>
