<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { TriangleAlert } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import AppShell from '@/components/AppShell.vue'
import { createReport } from '@/services/reports'
import { listTemplates, type TemplateSummary } from '@/services/templates'
import { listTeamMembers, listTeams, type Team, type TeamMemberSummary } from '@/services/teams'

const inputClass =
  'h-10 w-full rounded-md border border-zinc-200 bg-white px-3 outline-none transition focus:border-indigo-400 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const exerciseId = route.params.exerciseId as string
const token = computed(() => auth.token ?? '')

const templates = ref<TemplateSummary[]>([])
const teams = ref<Team[]>([])
const error = ref('')
const saving = ref(false)

const templateId = ref('')
const teamId = ref('')
const name = ref('')
const dueAtLocal = ref('')
const approvalRequired = ref(false)

// L7 writer assignment: members of the selected team; '' = anyone on the team.
const members = ref<TeamMemberSummary[]>([])
const assignedWriterId = ref('')

watch(teamId, async (team) => {
  members.value = []
  assignedWriterId.value = ''
  if (!team) return
  try {
    members.value = await listTeamMembers(token.value, exerciseId, team)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('reports.loadError')
  }
})

const canSubmit = computed(
  () => templateId.value !== '' && teamId.value !== '' && name.value.trim() !== '' && !saving.value,
)

onMounted(async () => {
  if (!auth.token) return
  try {
    ;[templates.value, teams.value] = await Promise.all([
      listTemplates(token.value, 'published'),
      listTeams(token.value, exerciseId),
    ])
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('reports.loadError')
  }
})

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  error.value = ''
  saving.value = true
  try {
    const created = await createReport(token.value, exerciseId, {
      template_id: templateId.value,
      team_id: teamId.value,
      name: name.value.trim(),
      due_at: dueAtLocal.value ? new Date(dueAtLocal.value).toISOString() : null,
      approval_required: approvalRequired.value,
      assigned_writer_id: assignedWriterId.value || null,
    })
    await router.push(`/exercises/${exerciseId}/reports/${created.id}`)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('reports.createError')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppShell :title="t('reports.createTitle')">
    <div class="mx-auto max-w-2xl">
      <div class="mb-6">
        <h1 class="text-2xl font-semibold tracking-tight">{{ t('reports.createTitle') }}</h1>
        <p class="mt-1 text-sm text-zinc-500">{{ t('reports.createSubtitle') }}</p>
      </div>

      <div
        v-if="error"
        class="alert-error mb-4 flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-400"
      >
        <TriangleAlert class="h-4 w-4 shrink-0" />
        <span>{{ error }}</span>
      </div>

      <form
        data-test="report-create-submit"
        class="space-y-5 rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900"
        @submit.prevent="submit"
      >
        <div>
          <label class="mb-1 block text-xs font-medium text-zinc-500">{{
            t('reports.name')
          }}</label>
          <input
            v-model="name"
            data-test="report-name"
            type="text"
            :placeholder="t('reports.namePlaceholder')"
            :class="inputClass"
          />
        </div>

        <div>
          <label class="mb-1 block text-xs font-medium text-zinc-500">{{
            t('reports.template')
          }}</label>
          <select v-model="templateId" data-test="report-template" :class="inputClass">
            <option value="" disabled>{{ t('reports.selectTemplate') }}</option>
            <option v-for="tpl in templates" :key="tpl.id" :value="tpl.id">
              {{ tpl.name }} · v{{ tpl.version }}
            </option>
          </select>
        </div>

        <div>
          <label class="mb-1 block text-xs font-medium text-zinc-500">{{
            t('reports.team')
          }}</label>
          <select v-model="teamId" data-test="report-team" :class="inputClass">
            <option value="" disabled>{{ t('reports.selectTeam') }}</option>
            <option v-for="team in teams" :key="team.id" :value="team.id">{{ team.name }}</option>
          </select>
        </div>

        <div v-if="teamId">
          <label class="mb-1 block text-xs font-medium text-zinc-500">{{
            t('reports.assignedWriter.label')
          }}</label>
          <select v-model="assignedWriterId" data-test="report-writer" :class="inputClass">
            <option value="">{{ t('reports.assignedWriter.anyone') }}</option>
            <option v-for="m in members" :key="m.user_id" :value="m.user_id">
              {{ m.display_name }}
            </option>
          </select>
        </div>

        <div>
          <label class="mb-1 block text-xs font-medium text-zinc-500">{{ t('reports.due') }}</label>
          <input v-model="dueAtLocal" type="datetime-local" :class="inputClass" />
        </div>

        <label class="flex items-center gap-2 text-sm">
          <input v-model="approvalRequired" type="checkbox" class="h-4 w-4 rounded" />
          {{ t('reports.approvalRequired') }}
        </label>

        <div class="flex justify-end gap-2 pt-2">
          <button
            type="button"
            class="flex h-9 items-center rounded-md border border-zinc-200 px-3 text-sm transition hover:bg-zinc-100 dark:border-zinc-800 dark:hover:bg-zinc-800"
            @click="router.push(`/exercises/${exerciseId}/reports`)"
          >
            {{ t('reports.cancel') }}
          </button>
          <button
            type="submit"
            :disabled="!canSubmit"
            class="flex h-9 items-center rounded-md bg-indigo-500 px-4 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:opacity-50"
          >
            {{ t('reports.create') }}
          </button>
        </div>
      </form>
    </div>
  </AppShell>
</template>
