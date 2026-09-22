import { apiGet } from '@/services/http'

/** One user in a search result — the member/writer/role-assignment picker data source. */
export interface UserSummary {
  id: string
  display_name: string
  email: string
  avatar_url: string | null
  is_global_admin: boolean
}

/** No open browse: an empty `q` returns no results server-side, so callers must debounce input. */
export const searchUsers = (token: string, q: string): Promise<UserSummary[]> =>
  apiGet<UserSummary[]>(`/api/v1/users?q=${encodeURIComponent(q)}`, token)
