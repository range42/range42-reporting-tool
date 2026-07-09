import { apiDelete, apiGet, apiPatch, apiPost } from '@/services/http'

export type TemplateStatus = 'draft' | 'published' | 'archived'
export type FieldType = 'rich_text' | 'choice'
export type GradeMode = 'numeric' | 'pass_fail' | 'rubric' | 'not_graded'

export interface ChoiceValue {
  code: string
  label: string
  position: number
  deprecated_at: string | null
}
export interface ChoiceConfig {
  selection: 'single' | 'multiple'
  values: ChoiceValue[]
}
export interface RubricCriterion {
  name: string
  description?: string
  weight: number
  max_score: number
}
export interface Section {
  id: string
  template_id: string
  position: number
  name: string
  description: string | null
  field_type: FieldType
  char_limit: number | null
  is_required: boolean
  grade_mode: GradeMode
  grade_min: number | null
  grade_max: number | null
  grade_weight: number
  rubric_criteria: RubricCriterion[] | null
  evaluation_criteria: string | null
  choice_config: ChoiceConfig | null
  mitre_attack_tags: string[]
  capec_tags: string[]
  cwe_tags: string[]
}
export type SectionInput = Omit<Section, 'id' | 'template_id' | 'position'>
export interface TemplateSummary {
  id: string
  lineage_id: string
  version: number
  name: string
  report_type: string
  description: string | null
  status: TemplateStatus
  section_count: number
}
export interface TemplateDetail {
  id: string
  lineage_id: string
  version: number
  name: string
  report_type: string
  description: string | null
  status: TemplateStatus
  metadata: Record<string, unknown> | null
  sections: Section[]
}
export interface TemplateVersion {
  id: string
  version: number
  status: TemplateStatus
  created_at: string
}
export interface TemplateBundle {
  schema_version: 1
  name: string
  report_type: string
  description: string | null
  sections: SectionInput[]
}

const base = '/api/v1/templates'

export const listTemplates = (token: string, status?: TemplateStatus): Promise<TemplateSummary[]> =>
  apiGet<TemplateSummary[]>(`${base}?per_page=100${status ? `&status=${status}` : ''}`, token)
export const getTemplate = (token: string, id: string): Promise<TemplateDetail> =>
  apiGet<TemplateDetail>(`${base}/${id}`, token)
export const createTemplate = (
  token: string,
  body: { name: string; report_type: string; description?: string | null },
): Promise<TemplateSummary> => apiPost<TemplateSummary>(base, body, token)
export const updateTemplate = (
  token: string,
  id: string,
  body: Partial<{ name: string; report_type: string; description: string | null }>,
): Promise<TemplateSummary> => apiPatch<TemplateSummary>(`${base}/${id}`, body, token)
export const deleteTemplate = (token: string, id: string): Promise<void> =>
  apiDelete(`${base}/${id}`, token)
export const publishTemplate = (token: string, id: string): Promise<TemplateSummary> =>
  apiPost<TemplateSummary>(`${base}/${id}/publish`, undefined, token)
export const cloneTemplate = (token: string, id: string): Promise<TemplateDetail> =>
  apiPost<TemplateDetail>(`${base}/${id}/clone`, undefined, token)
export const archiveTemplate = (token: string, id: string): Promise<TemplateSummary> =>
  apiPost<TemplateSummary>(`${base}/${id}/archive`, undefined, token)
export const listVersions = (token: string, id: string): Promise<TemplateVersion[]> =>
  apiGet<TemplateVersion[]>(`${base}/${id}/versions`, token)
export const exportTemplate = (token: string, id: string): Promise<TemplateBundle> =>
  apiGet<TemplateBundle>(`${base}/${id}/export`, token)
export const importTemplate = (token: string, bundle: TemplateBundle): Promise<TemplateDetail> =>
  apiPost<TemplateDetail>(`${base}/import`, bundle, token)
export const addSection = (token: string, tid: string, body: SectionInput): Promise<Section> =>
  apiPost<Section>(`${base}/${tid}/sections`, body, token)
export const updateSection = (
  token: string,
  tid: string,
  sid: string,
  body: Partial<SectionInput>,
): Promise<Section> => apiPatch<Section>(`${base}/${tid}/sections/${sid}`, body, token)
export const deleteSection = (token: string, tid: string, sid: string): Promise<void> =>
  apiDelete(`${base}/${tid}/sections/${sid}`, token)
export const reorderSections = (
  token: string,
  tid: string,
  orderedIds: string[],
): Promise<Section[]> =>
  apiPost<Section[]>(`${base}/${tid}/sections/reorder`, { ordered_ids: orderedIds }, token)
