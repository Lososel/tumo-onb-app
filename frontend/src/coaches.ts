import type { Locale } from './i18n'

/**
 * Coach names are entered in Latin script in the sheet ("Nazym", "Dana Akhmetova"). On the site
 * they are shown in Cyrillic: Russian spelling on the RU page, Kazakh spelling on the KK page.
 *
 * Known names come from this table (edit it to fix or add a spelling; keys are lowercase).
 * Any other Latin word is transliterated by rule, so a new coach is never shown in Latin.
 * Names already written in Cyrillic are left as they are.
 */
const KNOWN: Record<string, { ru: string; kk: string }> = {
  akbota: { ru: 'Акбота', kk: 'Ақбота' },
  akhmet: { ru: 'Ахмет', kk: 'Ахмет' },
  akhmetova: { ru: 'Ахметова', kk: 'Ахметова' },
  aigerim: { ru: 'Айгерим', kk: 'Әйгерім' },
  aizhan: { ru: 'Айжан', kk: 'Айжан' },
  alinur: { ru: 'Алинур', kk: 'Әлінұр' },
  aliya: { ru: 'Алия', kk: 'Әлия' },
  almas: { ru: 'Алмас', kk: 'Алмас' },
  arman: { ru: 'Арман', kk: 'Арман' },
  aruzhan: { ru: 'Аружан', kk: 'Аружан' },
  asel: { ru: 'Асель', kk: 'Әсел' },
  dana: { ru: 'Дана', kk: 'Дана' },
  dinara: { ru: 'Динара', kk: 'Динара' },
  elmira: { ru: 'Эльмира', kk: 'Эльмира' },
  gulim: { ru: 'Гулим', kk: 'Гүлім' },
  madina: { ru: 'Мадина', kk: 'Мадина' },
  moldir: { ru: 'Мольдир', kk: 'Мөлдір' },
  nazym: { ru: 'Назым', kk: 'Назым' },
  samat: { ru: 'Самат', kk: 'Самат' },
  telzhan: { ru: 'Тельжан', kk: 'Телжан' },
}

// Rule-based fallback for names not in KNOWN (multi-letter combinations first).
const DIGRAPHS: [string, string][] = [
  ['shch', 'щ'], ['zh', 'ж'], ['kh', 'х'], ['sh', 'ш'], ['ch', 'ч'], ['ts', 'ц'],
  ['ya', 'я'], ['yu', 'ю'], ['yo', 'ё'], ['ye', 'е'],
]
const LETTERS: Record<string, string> = {
  a: 'а', b: 'б', c: 'к', d: 'д', e: 'е', f: 'ф', g: 'г', h: 'х', i: 'и', j: 'дж', k: 'к',
  l: 'л', m: 'м', n: 'н', o: 'о', p: 'п', q: 'к', r: 'р', s: 'с', t: 'т', u: 'у', v: 'в',
  w: 'у', x: 'кс', z: 'з',
}

function transliterate(word: string): string {
  const w = word.toLowerCase()
  let out = ''
  for (let i = 0; i < w.length; ) {
    const di = DIGRAPHS.find(([lat]) => w.startsWith(lat, i))
    if (di) {
      out += di[1]
      i += di[0].length
      continue
    }
    const ch = w[i]
    const prevOut = out.slice(-1)
    if (ch === 'e' && i === 0) out += 'э' // Elnur -> Элнур: initial E
    // "i" after a vowel and before a consonant/end is a glide: Aibek -> Айбек, Aiym -> Айым
    else if (ch === 'i' && 'аеоуэ'.includes(prevOut) && !'aeou'.includes(w[i + 1] || '-')) out += 'й'
    // "y" is a vowel (ы) after a consonant or й, a glide (й) after a vowel: Nurym -> Нурым, Aiym -> Айым
    else if (ch === 'y') out += 'аеоуэ'.includes(prevOut) && prevOut !== '' ? 'й' : 'ы'
    else out += LETTERS[ch] ?? ch
    i += 1
  }
  return out.charAt(0).toUpperCase() + out.slice(1)
}

/** "Dana Akhmetova" -> "Дана Ахметова" (ru) / "Дана Ахметова" (kk); Cyrillic input unchanged. */
export function coachName(name: string | null, locale: Locale): string | null {
  if (!name) return name
  return name.replace(/[A-Za-z]+/g, (word) => KNOWN[word.toLowerCase()]?.[locale] ?? transliterate(word))
}
