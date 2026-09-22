<script setup lang="ts">
/**
 * Global-Admin tabbed shell for one exercise: Details, Team types, Teams, Roles.
 *
 * Only the active tab's panel is mounted, so switching tabs is also when that panel's own data
 * loads — no wasted requests for tabs the admin never opens.
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/AppShell.vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import {
  archiveExercise,
  getExercise,
  updateExercise,
  type Exercise,
  type ExerciseStatus,
} from '@/services/exercises'
import TeamTypesPanel from '@/views/settings/TeamTypesPanel.vue'
import TeamsPanel from '@/views/settings/TeamsPanel.vue'
import RoleAssignmentsPanel from '@/views/settings/RoleAssignmentsPanel.vue'

type Tab = 'details' | 'teamTypes' | 'teams' | 'roles'
const TABS: Tab[] = ['details', 'teamTypes', 'teams', 'roles']

const inputClass =
  'h-9 w-full rounded-md border border-zinc-200 bg-white px-2.5 text-sm outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-900'

const { t } = useI18n()
const route = useRoute()
const auth = useAuthStore()

const exerciseId = String(route.params.exerciseId)
const activeTab = ref<Tab>('details')
const exercise = ref<Exercise | null>(null)
const loading = ref(true)
const error = ref('')
const saving = ref(false)

const name = ref('')
const description = ref('')
const status = ref<ExerciseStatus>('draft')
const startsLocal = ref('')
const endsLocal = ref('')
const classification = ref('')
const tlp = ref('')

const canSave = computed(() => name.value.trim() !== '' && !saving.value)

function toLocal(iso: string | null): string {
  return iso ? iso.slice(0, 16) : ''
}

function hydrateForm(ex: Exercise): void {
  name.value = ex.name
  description.value = ex.description ?? ''
  status.value = ex.status
  startsLocal.value = toLocal(ex.starts_at)
  endsLocal.value = toLocal(ex.ends_at)
  classification.value = ex.classification ?? ''
  tlp.value = ex.tlp ?? ''
}

async function saveDetails(): Promise<void> {
  if (!canSave.value || !auth.token) return
  error.value = ''
  saving.value = true
  try {
    exercise.value = await updateExercise(auth.token, exerciseId, {
      name: name.value.trim(),
      description: description.value.trim() || null,
      status: status.value,
      starts_at: startsLocal.value ? new Date(startsLocal.value).toISOString() : null,
      ends_at: endsLocal.value ? new Date(endsLocal.value).toISOString() : null,
      classification: classification.value.trim() || null,
      tlp: tlp.value.trim() || null,
    })
    hydrateForm(exercise.value)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('exercises.settings.saveError')
  } finally {
    saving.value = false
  }
}

async function archive(): Promise<void> {
  if (!auth.token || !window.confirm(t('exercises.settings.archiveConfirm'))) return
  error.value = ''
  try {
    exercise.value = await archiveExercise(auth.token, exerciseId)
    hydrateForm(exercise.value)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('exercises.settings.archiveError')
  }
}

onMounted(async () => {
  if (!auth.token) {
    loading.value = false
    return
  }
  try {
    exercise.value = await getExercise(auth.token, exerciseId)
    hydrateForm(exercise.value)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('exercises.settings.loadError')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <AppShell :title="t('exercises.settings.title')">
    <div class="mb-6">
      <h1 class="text-2xl font-semibold tracking-tight">
        {{ exercise?.name ?? t('exercises.settings.title') }}
      </h1>
      <p class="mt-1 text-sm text-zinc-500">{{ t('exercises.settings.subtitle') }}</p>
    </div>

    <p v-if="loading" class="text-sm text-zinc-500">{{ t('exercises.settings.loading') }}</p>

    <template v-else>
      <div class="mb-6 flex gap-1 border-b border-zinc-200 dark:border-zinc-800">
        <button
          v-for="tab in TABS"
          :key="tab"
          type="button"
          :data-test="`tab-${tab}`"
          class="border-b-2 px-3 py-2 text-sm font-medium transition"
          :class="
            activeTab === tab
              ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
              : 'border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'
          "
          @click="activeTab = tab"
        >
          {{ t(`exercises.settings.tabs.${tab}`) }}
        </button>
      </div>

      <p v-if="error" data-test="details-error" class="mb-4 text-sm text-red-500">{{ error }}</p>

      <form
        v-if="activeTab === 'details'"
        data-test="details-form"
        class="max-w-2xl space-y-5"
        @submit.prevent="saveDetails"
      >
        <div>
          <label class="mb-1 block text-xs font-medium text-zinc-500">{{
            t('exercises.wizard.name')
          }}</label>
          <input v-model="name" data-test="details-name" :class="inputClass" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-zinc-500">{{
            t('exercises.wizard.description')
          }}</label>
          <textarea v-model="description" rows="2" :class="inputClass" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium text-zinc-500">{{
            t('exercises.settings.status')
          }}</label>
          <select v-model="status" data-test="details-status" :class="inputClass">
            <option value="draft">{{ t('exercises.status.draft') }}</option>
            <option value="active">{{ t('exercises.status.active') }}</option>
            <option value="archived">{{ t('exercises.status.archived') }}</option>
          </select>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="mb-1 block text-xs font-medium text-zinc-500">{{
              t('exercises.wizard.starts')
            }}</label>
            <input v-model="startsLocal" type="datetime-local" :class="inputClass" />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-zinc-500">{{
              t('exercises.wizard.ends')
            }}</label>
            <input v-model="endsLocal" type="datetime-local" :class="inputClass" />
          </div>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="mb-1 block text-xs font-medium text-zinc-500">{{
              t('exercises.wizard.classification')
            }}</label>
            <input v-model="classification" :class="inputClass" />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-zinc-500">{{
              t('exercises.wizard.tlp')
            }}</label>
            <input v-model="tlp" :class="inputClass" />
          </div>
        </div>
        <div class="flex justify-between pt-2">
          <button
            type="button"
            data-test="details-archive"
            class="flex h-9 items-center rounded-md border border-red-300 px-3 text-sm font-medium text-red-600 transition hover:bg-red-50 dark:border-red-500/40 dark:text-red-400 dark:hover:bg-red-500/10"
            @click="archive"
          >
            {{ t('exercises.settings.archive') }}
          </button>
          <button
            type="submit"
            data-test="details-save"
            :disabled="!canSave"
            class="flex h-9 items-center rounded-md bg-indigo-500 px-4 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:opacity-50"
          >
            {{ t('exercises.settings.save') }}
          </button>
        </div>
      </form>

      <TeamTypesPanel v-else-if="activeTab === 'teamTypes'" :exercise-id="exerciseId" />
      <TeamsPanel v-else-if="activeTab === 'teams'" :exercise-id="exerciseId" />
      <RoleAssignmentsPanel v-else-if="activeTab === 'roles'" :exercise-id="exerciseId" />
    </template>
  </AppShell>
</template>
