import { apiDelete, apiGet, apiPatch, apiPost } from '@/services/http'

export interface Role {
  id: string
  role_key: string
  display_label: string
  description: string | null
  permissions: string[]
  is_system: boolean
  created_at: string
  updated_at: string
}
export interface RoleCreate {
  role_key: string
  display_label: string
  description?: string | null
  permissions: string[]
}
export interface RoleUpdate {
  display_label?: string
  description?: string | null
  permissions?: string[]
}

export const listRoles = (token: string): Promise<Role[]> =>
  apiGet<Role[]>('/api/v1/roles?per_page=100', token)
export const listPermissions = (token: string): Promise<string[]> =>
  apiGet<string[]>('/api/v1/permissions', token)
export const createRole = (token: string, body: RoleCreate): Promise<Role> =>
  apiPost<Role>('/api/v1/roles', body, token)
export const updateRole = (token: string, id: string, body: RoleUpdate): Promise<Role> =>
  apiPatch<Role>(`/api/v1/roles/${id}`, body, token)
export const deleteRole = (token: string, id: string): Promise<void> =>
  apiDelete(`/api/v1/roles/${id}`, token)
