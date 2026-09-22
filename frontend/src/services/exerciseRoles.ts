import { apiDelete, apiGet, apiPost } from '@/services/http'

export interface ExerciseRoleAssignment {
  id: string
  exercise_id: string
  user_id: string
  role_key: string
  created_at: string
}

const base = (exerciseId: string): string => `/api/v1/exercises/${exerciseId}/roles`

export const listExerciseRoleAssignments = (
  token: string,
  exerciseId: string,
): Promise<ExerciseRoleAssignment[]> => apiGet<ExerciseRoleAssignment[]>(base(exerciseId), token)

export const grantExerciseRole = (
  token: string,
  exerciseId: string,
  userId: string,
  roleKey: string,
): Promise<ExerciseRoleAssignment> =>
  apiPost<ExerciseRoleAssignment>(base(exerciseId), { user_id: userId, role_key: roleKey }, token)

export const revokeExerciseRole = (
  token: string,
  exerciseId: string,
  assignmentId: string,
): Promise<void> => apiDelete(`${base(exerciseId)}/${assignmentId}`, token)
