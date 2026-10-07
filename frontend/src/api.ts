import axios from 'axios'

export type StatusCode = 'active_schedule' | 'waitlist' | 'schedule_pending' | 'schedule_changed' | 'coach_changed'

/** One learner's schedule card, as returned by POST /api/schedule/lookup. */
export interface Learner {
  full_name: string
  schedule: string | null
  coach_name: string | null
  room: string | null
  default_email: string | null
  /** null unless the backend has EXPOSE_TEMP_PASSWORD enabled */
  temp_password: string | null
  status_code: StatusCode | 'other'
  /** raw sheet text, shown as the badge when status_code is 'other' */
  status: string | null
}

export type LookupStatus = 'ok' | 'not_found' | 'inactive' | 'need_full_name' | 'too_many'

export interface LookupResponse {
  status: LookupStatus
  results: Learner[]
  data_updated_at: string | null
}

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 10_000,
})

/** POST keeps the learner's name out of URLs and server access logs. */
export async function lookupSchedule(query: string): Promise<LookupResponse> {
  const { data } = await http.post<LookupResponse>('/api/schedule/lookup', { query: query.trim() })
  return data
}

export type ErrorKind = 'rateLimited' | 'unavailable' | 'network'

export function errorKind(err: unknown): ErrorKind {
  if (axios.isAxiosError(err)) {
    if (err.response?.status === 429) return 'rateLimited'
    if (err.response?.status === 503) return 'unavailable'
  }
  return 'network'
}
