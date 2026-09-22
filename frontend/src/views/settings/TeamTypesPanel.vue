<script setup lang="ts">
/** Global-Admin CRUD over an exercise's team types. Nested inside ExerciseSettings.vue. */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Trash2 } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import {
  createTeamType,
  deleteTeamType,
  listTeamTypes,
  type TeamTypeConfig,
} from '@/services/teamTypes'

const props = defineProps<{ exerciseId: string }>()

const inputClass =
  'h-9 w-full rounded-md border border-zinc-200 bg-white px-2.5 text-sm outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-900'

const { t } = useI18n()
const auth = useAuthStore()

const types = ref<TeamTypeConfig[]>([])
const typeKey = ref('')
const displayLabel = ref('')
const defaultColor = ref('')
const isVisibleToOthers = ref(true)
const loading = ref(true)
const error = ref('')
const saving = ref(false)

const canSubmit = computed(
  () => typeKey.value.trim() !== '' && displayLabel.value.trim() !== '' && !saving.value,
)

async function load(): Promise<void> {
  if (!auth.token) return
  types.value = await listTeamTypes(auth.token, props.exerciseId)
}

async function submit(): Promise<void> {
  if (!canSubmit.value || !auth.token) return
  error.value = ''
  saving.value = true
  try {
    await createTeamType(auth.token, props.exerciseId, {
      type_key: typeKey.value.trim(),
      display_label: displayLabel.value.trim(),
      default_color: defaultColor.value.trim() || null,
      is_visible_to_others: isVisibleToOthers.value,
    })
    typeKey.value = ''
    displayLabel.value = ''
    defaultColor.value = ''
    isVisibleToOthers.value = true
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('exercises.settings.teamTypes.saveError')
  } finally {
    saving.value = false
  }
}

async function remove(id: string): Promise<void> {
  if (!auth.token) return
  error.value = ''
  try {
    await deleteTeamType(auth.token, props.exerciseId, id)
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('exercises.settings.teamTypes.deleteError')
  }
}

onMounted(async () => {
  try {
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('exercises.settings.teamTypes.loadError')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="space-y-6">
    <form data-test="type-form" class="flex flex-wrap items-end gap-2" @submit.prevent="submit">
      <div>
        <label class="mb-1 block text-xs text-zinc-500">{{
          t('exercises.settings.teamTypes.key')
        }}</label>
        <input v-model="typeKey" data-test="type-key" class="w-32" :class="inputClass" />
      </div>
      <div>
        <label class="mb-1 block text-xs text-zinc-500">{{
          t('exercises.settings.teamTypes.label')
        }}</label>
        <input v-model="displayLabel" data-test="type-label" class="w-40" :class="inputClass" />
      </div>
      <div>
        <label class="mb-1 block text-xs text-zinc-500">{{
          t('exercises.settings.teamTypes.color')
        }}</label>
        <input
          v-model="defaultColor"
          data-test="type-color"
          placeholder="#RRGGBB"
          class="w-28"
          :class="inputClass"
        />
      </div>
      <label class="mb-1.5 flex items-center gap-1.5 text-xs text-zinc-500">
        <input
          v-model="isVisibleToOthers"
          data-test="type-visible"
          type="checkbox"
          class="h-4 w-4"
        />
        {{ t('exercises.settings.teamTypes.visible') }}
      </label>
      <button
        type="submit"
        data-test="type-submit"
        :disabled="!canSubmit"
        class="flex h-9 items-center rounded-md bg-indigo-500 px-3 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:opacity-50"
      >
        {{ t('exercises.settings.teamTypes.add') }}
      </button>
    </form>

    <p v-if="error" data-test="type-error" class="text-sm text-red-500">{{ error }}</p>

    <p v-if="loading" class="text-sm text-zinc-500">{{ t('exercises.settings.loading') }}</p>
    <ul v-else class="space-y-1.5">
      <li
        v-for="tt in types"
        :key="tt.id"
        :data-test="`type-row-${tt.id}`"
        class="flex items-center justify-between rounded-lg border border-zinc-200 px-3.5 py-2.5 dark:border-zinc-800"
      >
        <span class="text-sm">
          <span
            v-if="tt.default_color"
            class="mr-2 inline-block h-3 w-3 rounded-full align-middle"
            :style="{ backgroundColor: tt.default_color }"
          />
          {{ tt.display_label }} <code class="text-xs text-zinc-500">({{ tt.type_key }})</code>
        </span>
        <button
          type="button"
          :data-test="`type-delete-${tt.id}`"
          class="flex h-7 items-center gap-1 rounded-md px-2 text-xs text-red-500 transition hover:bg-red-500/10"
          @click="remove(tt.id)"
        >
          <Trash2 class="h-3.5 w-3.5" />
        </button>
      </li>
    </ul>
  </div>
</template>
