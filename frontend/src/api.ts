import axios from 'axios'

export interface Learner {
  full_name: string
  schedule: string | null
  schedule_kk: string | null
  self_study_day: string | null
  self_study_day_kk: string | null
  coach: string | null
  coach_email: string | null
  stage: string | null
  stage_code: 'self_study' | 'workshop' | 'project' | null
  status: string | null
  status_code: 'coach_unchanged' | 'coach_changed' | 'schedule_changed' | 'unchanged' | 'pending' | null
  note: string | null
  note_kk: string | null
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
