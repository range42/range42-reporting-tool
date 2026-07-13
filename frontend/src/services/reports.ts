import { apiDelete, apiGet, apiPatch, apiPost } from '@/services/http'
import type { ChoiceConfig, FieldType } from '@/services/templates'

export type ReportStatus = 'draft' | 'submitted'

export interface Report {
  id: string
  exercise_id: string
  team_id: string
  template_id: string
  template_version_at_creation: number
  name: string
  description: string | null
  status: ReportStatus
  approval_required: boolean
  due_at: string | null
  submitted_at: string | null
  assigned_writer_id: string | null
  section_count: number
}

export interface ReportSection {
  id: string
  report_id: string
  section_def_id: string
  position: number
  name: string
  description: string | null
  field_type: FieldType
  is_required: boolean
  char_limit: number | null
  choice_config: ChoiceConfig | null
  content: string | null
  content_plain: string | null
  char_count: number
  choice_values: string[] | null
  version: number
  last_edited_by: string | null
  last_edited_at: string | null
  created_at: string
  updated_at: string
}

export interface ReportDetail {
  id: string
  exercise_id: string
  team_id: string
  template_id: string
  template_version_at_creation: number
  name: string
  description: string | null
  status: ReportStatus
  approval_required: boolean
  due_at: string | null
  submitted_at: string | null
  assigned_writer_id: string | null
  writer_notes: string | null
  metadata: Record<string, unknown> | null
  sections: ReportSection[]
}

export type SectionAnswerBody =
  | { kind: 'rich_text'; content: string }
  | { kind: 'choice'; choice_values: string[] }

export interface CreateReportInput {
  template_id: string
  team_id: string
  name: string
  description?: string | null
  due_at?: string | null
  approval_required?: boolean
  assigned_writer_id?: string | null
}

export type UpdateReportInput = Partial<{
  name: string
  description: string | null
  due_at: string | null
  approval_required: boolean
  assigned_writer_id: string | null
}>

const base = (exerciseId: string): string => `/api/v1/exercises/${exerciseId}/reports`

export const listReports = (
  token: string,
  exerciseId: string,
  params?: { team_id?: string; status?: ReportStatus },
): Promise<Report[]> => {
  const qs = new URLSearchParams({ per_page: '100' })
  if (params?.team_id) qs.set('team_id', params.team_id)
  if (params?.status) qs.set('status', params.status)
  return apiGet<Report[]>(`${base(exerciseId)}?${qs.toString()}`, token)
}
export const getReport = (token: string, exerciseId: string, rid: string): Promise<ReportDetail> =>
  apiGet<ReportDetail>(`${base(exerciseId)}/${rid}`, token)
export const createReport = (
  token: string,
  exerciseId: string,
  body: CreateReportInput,
): Promise<ReportDetail> => apiPost<ReportDetail>(base(exerciseId), body, token)
export const updateReport = (
  token: string,
  exerciseId: string,
  rid: string,
  body: UpdateReportInput,
): Promise<Report> => apiPatch<Report>(`${base(exerciseId)}/${rid}`, body, token)
export const deleteReport = (token: string, exerciseId: string, rid: string): Promise<void> =>
  apiDelete(`${base(exerciseId)}/${rid}`, token)
export const saveSection = (
  token: string,
  exerciseId: string,
  rid: string,
  sid: string,
  body: { version: number; body: SectionAnswerBody },
): Promise<ReportSection> =>
  apiPatch<ReportSection>(`${base(exerciseId)}/${rid}/sections/${sid}`, body, token)
export const submitReport = (
  token: string,
  exerciseId: string,
  rid: string,
): Promise<ReportDetail> =>
  apiPost<ReportDetail>(`${base(exerciseId)}/${rid}/submit`, undefined, token)
