import axios from 'axios'

export interface SelfStudy {
  days: string
  time: string
}

export interface Workshop {
  name: string
  teacher: string | null
  room: string | null
  days: string
  time: string
}

export interface StudentDashboard {
  first_name: string
  last_name: string
  self_study: SelfStudy | null
  workshops: Workshop[]
  links: { whatsapp: string | null }
}

export interface LookupResponse {
  status: 'ok' | 'not_found' | 'inactive'
  message: string
  students: StudentDashboard[]
  data_updated_at: string | null
}

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 10_000,
})

/** Uses POST so the student's name never appears in URLs or server access logs. */
export async function lookupStudent(firstName: string, lastName: string): Promise<LookupResponse> {
  const { data } = await http.post<LookupResponse>('/api/students/lookup', {
    first_name: firstName.trim(),
    last_name: lastName.trim(),
  })
  return data
}

export function errorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    if (err.response?.status === 429) return 'Too many tries — please wait a minute and try again.'
    if (err.response?.status === 503) return 'The schedule is being updated. Please try again in a moment.'
    if (err.response?.status === 422) return 'Please enter both your first and last name.'
  }
  return "We couldn't reach TUMO right now. Check your connection and try again."
}
