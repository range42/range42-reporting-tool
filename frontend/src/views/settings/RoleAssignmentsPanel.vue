<script setup lang="ts">
/** Global-Admin role-assignment CRUD for an exercise. */
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { UserMinus } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import {
  grantExerciseRole,
  listExerciseRoleAssignments,
  revokeExerciseRole,
  type ExerciseRoleAssignment,
} from '@/services/exerciseRoles'
import { listRoles, type Role } from '@/services/roles'
import { searchUsers, type UserSummary } from '@/services/users'

const props = defineProps<{ exerciseId: string }>()

const inputClass =
  'h-9 w-full rounded-md border border-zinc-200 bg-white px-2.5 text-sm outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-900'

const { t } = useI18n()
const auth = useAuthStore()

const assignments = ref<ExerciseRoleAssignment[]>([])
const roles = ref<Role[]>([])
const query = ref('')
const candidates = ref<UserSummary[]>([])
const pickedUserId = ref('')
const roleKey = ref('')
const knownUsers = reactive(new Map<string, UserSummary>())
const loading = ref(true)
const error = ref('')
const granting = ref(false)

const pickedLabel = computed(() => {
  const u = knownUsers.get(pickedUserId.value)
  return u ? `${u.display_name} (${u.email})` : ''
})
const canGrant = computed(
  () => pickedUserId.value !== '' && roleKey.value !== '' && !granting.value,
)

function roleLabel(key: string): string {
  return roles.value.find((r) => r.role_key === key)?.display_label ?? key
}

async function load(): Promise<void> {
  if (!auth.token) return
  assignments.value = await listExerciseRoleAssignments(auth.token, props.exerciseId)
}

async function search(): Promise<void> {
  if (!auth.token || query.value.trim() === '') {
    candidates.value = []
    return
  }
  try {
    candidates.value = await searchUsers(auth.token, query.value.trim())
    for (const c of candidates.value) knownUsers.set(c.id, c)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('exercises.settings.roles.searchError')
  }
}

function pick(u: UserSummary): void {
  pickedUserId.value = u.id
  knownUsers.set(u.id, u)
  candidates.value = []
  query.value = ''
}

async function grant(): Promise<void> {
  if (!canGrant.value || !auth.token) return
  error.value = ''
  granting.value = true
  try {
    await grantExerciseRole(auth.token, props.exerciseId, pickedUserId.value, roleKey.value)
    pickedUserId.value = ''
    roleKey.value = ''
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('exercises.settings.roles.grantError')
  } finally {
    granting.value = false
  }
}

async function revoke(id: string): Promise<void> {
  if (!auth.token) return
  error.value = ''
  try {
    await revokeExerciseRole(auth.token, props.exerciseId, id)
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('exercises.settings.roles.revokeError')
  }
}

onMounted(async () => {
  if (!auth.token) {
    loading.value = false
    return
  }
  try {
    ;[assignments.value, roles.value] = await Promise.all([
      listExerciseRoleAssignments(auth.token, props.exerciseId),
      listRoles(auth.token),
    ])
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('exercises.settings.roles.loadError')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-end gap-2">
      <div class="relative">
        <label class="mb-1 block text-xs text-zinc-500">{{
          t('exercises.settings.roles.person')
        }}</label>
        <input
          v-model="query"
          data-test="role-search"
          :placeholder="pickedLabel || t('exercises.settings.roles.searchPlaceholder')"
          class="w-56"
          :class="inputClass"
          @input="search"
        />
        <ul
          v-if="candidates.length"
          class="absolute z-10 mt-1 w-56 space-y-0.5 rounded-md border border-zinc-200 bg-white p-1 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        >
          <li
            v-for="c in candidates"
            :key="c.id"
            :data-test="`role-candidate-${c.id}`"
            class="cursor-pointer rounded px-2 py-1 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            @click="pick(c)"
          >
            {{ c.display_name }} ({{ c.email }})
          </li>
        </ul>
      </div>
      <div>
        <label class="mb-1 block text-xs text-zinc-500">{{
          t('exercises.settings.roles.role')
        }}</label>
        <select v-model="roleKey" data-test="role-select" class="w-40" :class="inputClass">
          <option value="" disabled>{{ t('exercises.settings.roles.rolePlaceholder') }}</option>
          <option v-for="r in roles" :key="r.role_key" :value="r.role_key">
            {{ r.display_label }}
          </option>
        </select>
      </div>
      <button
        type="button"
        data-test="role-grant"
        :disabled="!canGrant"
        class="flex h-9 items-center rounded-md bg-indigo-500 px-3 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:opacity-50"
        @click="grant"
      >
        {{ t('exercises.settings.roles.grant') }}
      </button>
    </div>

    <p v-if="error" data-test="role-error" class="text-sm text-red-500">{{ error }}</p>
    <p v-if="loading" class="text-sm text-zinc-500">{{ t('exercises.settings.loading') }}</p>

    <ul v-else class="space-y-1.5">
      <li
        v-for="a in assignments"
        :key="a.id"
        :data-test="`role-row-${a.id}`"
        class="flex items-center justify-between rounded-lg border border-zinc-200 px-3.5 py-2.5 text-sm dark:border-zinc-800"
      >
        <span
          >{{ a.user_display_name }} —
          <code class="text-xs text-zinc-500">{{ roleLabel(a.role_key) }}</code></span
        >
        <button
          type="button"
          :data-test="`role-revoke-${a.id}`"
          class="flex h-7 items-center gap-1 rounded-md px-2 text-xs text-red-500 transition hover:bg-red-500/10"
          @click="revoke(a.id)"
        >
          <UserMinus class="h-3.5 w-3.5" />
        </button>
      </li>
    </ul>
  </div>
</template>
