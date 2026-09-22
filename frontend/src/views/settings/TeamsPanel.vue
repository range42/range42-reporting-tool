<script setup lang="ts">
/** Global-Admin CRUD over an exercise's teams, with per-team member management inline. */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown, ChevronRight, Trash2 } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import { createTeam, deleteTeam, listTeams, type Team } from '@/services/teams'
import { listTeamTypes, type TeamTypeConfig } from '@/services/teamTypes'
import MembersPanel from '@/views/settings/MembersPanel.vue'

const props = defineProps<{ exerciseId: string }>()

const inputClass =
  'h-9 w-full rounded-md border border-zinc-200 bg-white px-2.5 text-sm outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-900'

const { t } = useI18n()
const auth = useAuthStore()

const teams = ref<Team[]>([])
const teamTypes = ref<TeamTypeConfig[]>([])
const name = ref('')
const teamType = ref('')
const color = ref('')
const expanded = ref<string | null>(null)
const loading = ref(true)
const error = ref('')
const saving = ref(false)

const canSubmit = computed(() => name.value.trim() !== '' && teamType.value !== '' && !saving.value)

async function load(): Promise<void> {
  if (!auth.token) return
  teams.value = await listTeams(auth.token, props.exerciseId)
}

async function submit(): Promise<void> {
  if (!canSubmit.value || !auth.token) return
  error.value = ''
  saving.value = true
  try {
    await createTeam(auth.token, props.exerciseId, {
      name: name.value.trim(),
      team_type: teamType.value,
      color: color.value.trim() || null,
    })
    name.value = ''
    teamType.value = ''
    color.value = ''
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('exercises.settings.teams.saveError')
  } finally {
    saving.value = false
  }
}

async function remove(id: string): Promise<void> {
  if (!auth.token) return
  error.value = ''
  try {
    await deleteTeam(auth.token, props.exerciseId, id)
    if (expanded.value === id) expanded.value = null
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('exercises.settings.teams.deleteError')
  }
}

function toggle(id: string): void {
  expanded.value = expanded.value === id ? null : id
}

onMounted(async () => {
  if (!auth.token) {
    loading.value = false
    return
  }
  try {
    ;[teams.value, teamTypes.value] = await Promise.all([
      listTeams(auth.token, props.exerciseId),
      listTeamTypes(auth.token, props.exerciseId),
    ])
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('exercises.settings.teams.loadError')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="space-y-6">
    <form data-test="team-form" class="flex flex-wrap items-end gap-2" @submit.prevent="submit">
      <div>
        <label class="mb-1 block text-xs text-zinc-500">{{
          t('exercises.settings.teams.name')
        }}</label>
        <input v-model="name" data-test="team-name" class="w-40" :class="inputClass" />
      </div>
      <div>
        <label class="mb-1 block text-xs text-zinc-500">{{
          t('exercises.settings.teams.type')
        }}</label>
        <select v-model="teamType" data-test="team-type" class="w-36" :class="inputClass">
          <option value="" disabled>{{ t('exercises.settings.teams.typePlaceholder') }}</option>
          <option v-for="tt in teamTypes" :key="tt.id" :value="tt.type_key">
            {{ tt.display_label }}
          </option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs text-zinc-500">{{
          t('exercises.settings.teams.color')
        }}</label>
        <input
          v-model="color"
          data-test="team-color"
          placeholder="#RRGGBB"
          class="w-28"
          :class="inputClass"
        />
      </div>
      <button
        type="submit"
        data-test="team-submit"
        :disabled="!canSubmit"
        class="flex h-9 items-center rounded-md bg-indigo-500 px-3 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:opacity-50"
      >
        {{ t('exercises.settings.teams.add') }}
      </button>
    </form>

    <p v-if="error" data-test="team-error" class="text-sm text-red-500">{{ error }}</p>
    <p v-if="loading" class="text-sm text-zinc-500">{{ t('exercises.settings.loading') }}</p>

    <ul v-else class="space-y-1.5">
      <li
        v-for="team in teams"
        :key="team.id"
        :data-test="`team-row-${team.id}`"
        class="rounded-lg border border-zinc-200 dark:border-zinc-800"
      >
        <div class="flex items-center justify-between px-3.5 py-2.5">
          <button
            type="button"
            :data-test="`team-expand-${team.id}`"
            class="flex flex-1 items-center gap-2 text-left text-sm"
            @click="toggle(team.id)"
          >
            <component
              :is="expanded === team.id ? ChevronDown : ChevronRight"
              class="h-4 w-4 text-zinc-400"
            />
            <span
              v-if="team.color"
              class="inline-block h-3 w-3 rounded-full"
              :style="{ backgroundColor: team.color }"
            />
            {{ team.name }}
            <code class="text-xs text-zinc-500">({{ team.team_type }})</code>
          </button>
          <button
            type="button"
            :data-test="`team-delete-${team.id}`"
            class="flex h-7 items-center gap-1 rounded-md px-2 text-xs text-red-500 transition hover:bg-red-500/10"
            @click="remove(team.id)"
          >
            <Trash2 class="h-3.5 w-3.5" />
          </button>
        </div>
        <div v-if="expanded === team.id" class="border-t border-zinc-100 p-3 dark:border-zinc-800">
          <MembersPanel :exercise-id="exerciseId" :team-id="team.id" />
        </div>
      </li>
    </ul>
  </div>
</template>
