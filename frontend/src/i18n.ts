import { computed, ref, watchEffect } from 'vue'
import kk from './locales/kk'
import ru, { type Messages } from './locales/ru'

/**
 * Tiny i18n: two locales, typed messages, no dependency. The chosen language is
 * remembered per browser (a convenience only — the page works without storage).
 */
export type Locale = 'ru' | 'kk'

const MESSAGES: Record<Locale, Messages> = { ru, kk }
const KEY = 'tumo.locale'

function initialLocale(): Locale {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved === 'ru' || saved === 'kk') return saved
  } catch {
    /* storage unavailable */
  }
  return navigator.language?.toLowerCase().startsWith('kk') ? 'kk' : 'ru'
}

export const locale = ref<Locale>(initialLocale())
export const t = computed<Messages>(() => MESSAGES[locale.value])

export function setLocale(next: Locale) {
  locale.value = next
  try {
    localStorage.setItem(KEY, next)
  } catch {
    /* ignore */
  }
}

watchEffect(() => {
  document.documentElement.lang = locale.value
  document.title = t.value.meta.title
})

export function format(template: string, params: Record<string, string>) {
  return template.replace(/\{(\w+)\}/g, (_, k: string) => params[k] ?? '')
}

// Russian weekday names (as the team writes them in the sheet) -> Kazakh.
// JS `\b` is ASCII-only, so abbreviations are bounded with explicit Cyrillic lookarounds.
const L = '[а-яё]'
const day = (full: string, abbr: string) => new RegExp(`${full}${L}*|(?<!${L})${abbr}(?!${L})`, 'gi')
const WEEKDAYS_KK: [RegExp, string][] = [
  [day('понедельник', 'пн'), 'Дүйсенбі'],
  [day('вторник', 'вт'), 'Сейсенбі'],
  [day('сред[аыу]', 'ср'), 'Сәрсенбі'],
  [day('четверг', 'чт'), 'Бейсенбі'],
  [day('пятниц', 'пт'), 'Жұма'],
  [day('суббот', 'сб'), 'Сенбі'],
  [day('воскресень', 'вс'), 'Жексенбі'],
]

/** Picks the Kazakh override if the sheet has one, otherwise translates weekday names. */
export function localized(value: string | null, kkValue: string | null = null): string | null {
  if (locale.value !== 'kk' || !value) return value
  if (kkValue) return kkValue
  return WEEKDAYS_KK.reduce((s, [re, kkDay]) => s.replace(re, kkDay), value)
}
