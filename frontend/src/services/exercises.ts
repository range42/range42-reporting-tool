import { apiDelete, apiGet, apiPatch, apiPost } from '@/services/http'

export type ExerciseStatus = 'draft' | 'active' | 'archived'

export interface Exercise {
  id: string
  name: string
  description: string | null
  status: ExerciseStatus
  starts_at: string | null
  ends_at: string | null
  classification: string | null
  tlp: string | null
  classification_caveats: string[] | null
  created_by: string
  created_at: string
  updated_at: string
}

export interface ExerciseCreateInput {
  name: string
  description?: string | null
  starts_at?: string | null
  ends_at?: string | null
  classification?: string | null
  tlp?: string | null
}

export type ExerciseUpdateInput = Partial<{
  name: string
  description: string | null
  status: ExerciseStatus
  starts_at: string | null
  ends_at: string | null
  classification: string | null
  tlp: string | null
}>

export const listExercises = (token: string, page = 1, perPage = 25): Promise<Exercise[]> =>
  apiGet<Exercise[]>(`/api/v1/exercises?page=${page}&per_page=${perPage}`, token)

export const getExercise = (token: string, id: string): Promise<Exercise> =>
  apiGet<Exercise>(`/api/v1/exercises/${id}`, token)

export const createExercise = (token: string, body: ExerciseCreateInput): Promise<Exercise> =>
  apiPost<Exercise>('/api/v1/exercises', body, token)

export const updateExercise = (
  token: string,
  id: string,
  body: ExerciseUpdateInput,
): Promise<Exercise> => apiPatch<Exercise>(`/api/v1/exercises/${id}`, body, token)

/** Soft-delete: the exercise moves to `status: 'archived'`, it is not removed. */
export const archiveExercise = (token: string, id: string): Promise<Exercise> =>
  apiDelete<Exercise>(`/api/v1/exercises/${id}`, token)

/** The caller's own capabilities within an exercise (drives coarse approver gating). */
export interface MeCapabilities {
  is_global_admin: boolean
  capabilities: string[]
}

export const getMyCapabilities = (token: string, exerciseId: string): Promise<MeCapabilities> =>
  apiGet<MeCapabilities>(`/api/v1/exercises/${exerciseId}/me`, token)
