/** Public contact details shown in the support block. Edit here to update the site. */
export const contacts = {
  email: 'info.astana@tumo.kz',
  whatsappDisplay: '+7 775 903 4013',
  whatsappNumber: '77759034013',
  instagram: 'tumo_astana',
  website: 'astana.tumo.kz',
}

export function whatsappLink(message = '') {
  const text = message ? `?text=${encodeURIComponent(message)}` : ''
  return `https://wa.me/${contacts.whatsappNumber}${text}`
}
