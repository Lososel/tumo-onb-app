import { ref } from 'vue'
import type { LookupResponse } from './api'

/**
 * Holds the current lookup result in memory, mirrored to sessionStorage so a page refresh
 * keeps the dashboard. Nothing is written to localStorage and the name never goes in the URL.
 */
const KEY = 'tumo.lookup'

function restore(): LookupResponse | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as LookupResponse) : null
  } catch {
    return null
  }
}

export const lookupResult = ref<LookupResponse | null>(restore())

export function setLookupResult(result: LookupResponse | null) {
  lookupResult.value = result
  try {
    if (result) sessionStorage.setItem(KEY, JSON.stringify(result))
    else sessionStorage.removeItem(KEY)
  } catch {
    /* storage unavailable (private mode) — in-memory state still works */
  }
}
