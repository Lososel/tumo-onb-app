/**
 * Proper case for people's names: first letter of each word upper case, the rest lower case.
 * Works for Russian and Kazakh letters: "БАТЫРЖАН НҰРАЛИ АМАНГЕЛДІҰЛЫ" -> "Батыржан Нұрали Амангелдіұлы".
 * Hyphenated and apostrophe parts are capitalized too ("анна-мария" -> "Анна-Мария"); extra spaces
 * are collapsed.
 */
export function titleCase(name: string): string {
  return name
    .trim()
    .replace(/\s+/g, ' ')
    .toLowerCase()
    .replace(/(^|[\s\-‐'’ʼ(])(\p{L})/gu, (_, sep: string, letter: string) => sep + letter.toUpperCase())
}
