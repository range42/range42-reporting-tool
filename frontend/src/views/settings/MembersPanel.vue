<script setup lang="ts">
/** Global-Admin member management for one team. Nested inside TeamsPanel.vue. */
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { UserMinus } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import {
  addTeamMember,
  listTeamMembers,
  removeTeamMember,
  type TeamMemberSummary,
} from '@/services/teams'
import { searchUsers, type UserSummary } from '@/services/users'

const props = defineProps<{ exerciseId: string; teamId: string }>()

const { t } = useI18n()
const auth = useAuthStore()

const members = ref<TeamMemberSummary[]>([])
const query = ref('')
const candidates = ref<UserSummary[]>([])
const error = ref('')

async function load(): Promise<void> {
  if (!auth.token) return
  members.value = await listTeamMembers(auth.token, props.exerciseId, props.teamId)
}

watch(query, async (q) => {
  if (!auth.token || q.trim() === '') {
    candidates.value = []
    return
  }
  try {
    candidates.value = await searchUsers(auth.token, q.trim())
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('exercises.settings.teams.searchError')
  }
})

async function add(userId: string): Promise<void> {
  if (!auth.token) return
  error.value = ''
  try {
    await addTeamMember(auth.token, props.exerciseId, props.teamId, userId)
    query.value = ''
    candidates.value = []
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('exercises.settings.teams.addMemberError')
  }
}

async function remove(userId: string): Promise<void> {
  if (!auth.token) return
  error.value = ''
  try {
    await removeTeamMember(auth.token, props.exerciseId, props.teamId, userId)
    await load()
  } catch (e) {
    error.value =
      e instanceof ApiError ? e.message : t('exercises.settings.teams.removeMemberError')
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-3 rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800/40">
    <div class="relative">
      <input
        v-model="query"
        data-test="member-search"
        :placeholder="t('exercises.settings.teams.searchPlaceholder')"
        class="h-9 w-full rounded-md border border-zinc-200 bg-white px-2.5 text-sm outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-900"
      />
      <ul
        v-if="candidates.length"
        class="mt-1 space-y-0.5 rounded-md border border-zinc-200 bg-white p-1 text-sm dark:border-zinc-700 dark:bg-zinc-900"
      >
        <li
          v-for="c in candidates"
          :key="c.id"
          :data-test="`member-candidate-${c.id}`"
          class="cursor-pointer rounded px-2 py-1 hover:bg-zinc-100 dark:hover:bg-zinc-800"
          @click="add(c.id)"
        >
          {{ c.display_name }} ({{ c.email }})
        </li>
      </ul>
    </div>

    <p v-if="error" data-test="member-error" class="text-sm text-red-500">{{ error }}</p>

    <p v-if="members.length === 0" class="text-sm text-zinc-500">
      {{ t('exercises.settings.teams.noMembers') }}
    </p>
    <ul v-else class="space-y-1">
      <li
        v-for="m in members"
        :key="m.id"
        :data-test="`member-row-${m.id}`"
        class="flex items-center justify-between text-sm"
      >
        <span>{{ m.display_name }} ({{ m.email }})</span>
        <button
          type="button"
          :data-test="`member-remove-${m.id}`"
          class="flex h-6 items-center gap-1 rounded-md px-1.5 text-xs text-red-500 transition hover:bg-red-500/10"
          @click="remove(m.user_id)"
        >
          <UserMinus class="h-3.5 w-3.5" />
        </button>
      </li>
    </ul>
  </div>
</template>
