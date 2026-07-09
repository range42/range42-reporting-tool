import { apiGet } from '@/services/http'

export interface Exercise {
  id: string
  name: string
  description: string | null
  status: 'draft' | 'active' | 'archived'
  created_at: string
  updated_at: string
}

export const listExercises = (token: string, page = 1, perPage = 25): Promise<Exercise[]> =>
  apiGet<Exercise[]>(`/api/v1/exercises?page=${page}&per_page=${perPage}`, token)
