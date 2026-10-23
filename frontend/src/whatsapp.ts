/**
 * WhatsApp communities, one per onboarding time slot. To add or change a group, edit
 * COMMUNITIES and put its QR code in public/whatsapp/<key>.svg.
 */
export type DayPair = 'mon-thu' | 'tue-fri'

export interface Community {
  key: string // also the QR file name: /whatsapp/<key>.svg
  days: DayPair
  start: string // "HH:MM"
  end: string
  url: string
}

export const COMMUNITIES: Community[] = [
  { key: 'mon-thu-1030', days: 'mon-thu', start: '10:30', end: '12:30', url: 'https://chat.whatsapp.com/Bux2Ep5f0AK3lFvTNE9MLT' },
  { key: 'mon-thu-1430', days: 'mon-thu', start: '14:30', end: '16:30', url: 'https://chat.whatsapp.com/CdKA9oHpWxdDp4e1RZOBJU' },
  { key: 'mon-thu-1630', days: 'mon-thu', start: '16:30', end: '18:30', url: 'https://chat.whatsapp.com/HO5hTYGAQfX8kyShNzdd5J' },
  { key: 'tue-fri-1030', days: 'tue-fri', start: '10:30', end: '12:30', url: 'https://chat.whatsapp.com/LpF7RL8VbQb9GTLLSq8m6k' },
  { key: 'tue-fri-1430', days: 'tue-fri', start: '14:30', end: '16:30', url: 'https://chat.whatsapp.com/KDtxPBsHlOmG07wX6BIM7Q' },
  { key: 'tue-fri-1630', days: 'tue-fri', start: '16:30', end: '18:30', url: 'https://chat.whatsapp.com/Ii5VjHgsA2L0DO7UNM1IgH' },
]

// Weekday names/abbreviations as the team writes them (RU and KK). Bounded with Cyrillic
// lookarounds because JS `\b` is ASCII-only.
const L = '[а-яёәғқңөұүһі]'
const has = (s: string, ...words: string[]) =>
  words.some((w) => new RegExp(`(?<!${L})${w}`, 'i').test(s))

function dayPair(schedule: string): DayPair | null {
  const mon = has(schedule, 'понедельник', 'пн(?!' + L + ')', 'дүйсенбі', 'дс(?!' + L + ')')
  const thu = has(schedule, 'четверг', 'чт(?!' + L + ')', 'бейсенбі', 'бс(?!' + L + ')')
  const tue = has(schedule, 'вторник', 'вт(?!' + L + ')', 'сейсенбі', 'сс(?!' + L + ')')
  const fri = has(schedule, 'пятниц', 'пт(?!' + L + ')', 'жұма', 'жм(?!' + L + ')')
  if (mon && thu && !tue && !fri) return 'mon-thu'
  if (tue && fri && !mon && !thu) return 'tue-fri'
  return null
}

function startTime(schedule: string): string | null {
  const m = schedule.match(/(\d{1,2})[:.](\d{2})/)
  return m ? `${m[1].padStart(2, '0')}:${m[2]}` : null
}

/** The community for a schedule like "Понедельник, Четверг : 10:30–12:30" or "Пн/Чт 10:30-12:30". */
export function communityFor(schedule: string | null): Community | null {
  if (!schedule) return null
  const days = dayPair(schedule)
  const start = startTime(schedule)
  return COMMUNITIES.find((c) => c.days === days && c.start === start) ?? null
}
