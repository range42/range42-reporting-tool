<script setup lang="ts">
import { onMounted, ref, type Component } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Activity, Archive, ArrowRight, LogOut, Pencil, TriangleAlert } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { listExercises, type Exercise } from '@/services/exercises'
import { ApiError } from '@/services/http'
import AppShell from '@/components/AppShell.vue'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const exercises = ref<Exercise[]>([])
const loading = ref(true)
const error = ref('')

type StatusStyle = { icon: Component; tile: string; pill: string; dim?: string }
const statusStyle: Record<Exercise['status'], StatusStyle> = {
  active: {
    icon: Activity,
    tile: 'bg-emerald-500/10 text-emerald-500',
    pill: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300',
  },
  draft: {
    icon: Pencil,
    tile: 'bg-zinc-200 text-zinc-500 dark:bg-zinc-800',
    pill: 'bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300',
  },
  archived: {
    icon: Archive,
    tile: 'bg-zinc-200 text-zinc-500 dark:bg-zinc-800',
    pill: 'bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300',
    dim: 'opacity-60',
  },
}

onMounted(async () => {
  if (!auth.token) {
    loading.value = false
    return
  }
  try {
    exercises.value = await listExercises(auth.token)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('exercises.loadError')
  } finally {
    loading.value = false
  }
})

async function logout(): Promise<void> {
  await auth.logout()
  await router.push('/login')
}
</script>

<template>
  <AppShell :title="t('exercises.title')">
    <template #actions>
      <RouterLink
        v-if="auth.isAdmin"
        to="/settings/templates"
        class="flex h-9 items-center rounded-md border border-zinc-200 px-3 text-sm font-medium transition hover:bg-zinc-100 dark:border-zinc-800 dark:hover:bg-zinc-800"
      >
        {{ t('exercises.manageTemplates') }}
      </RouterLink>
      <RouterLink
        v-if="auth.isAdmin"
        to="/settings/roles"
        class="flex h-9 items-center rounded-md border border-zinc-200 px-3 text-sm font-medium transition hover:bg-zinc-100 dark:border-zinc-800 dark:hover:bg-zinc-800"
      >
        {{ t('exercises.manageRoles') }}
      </RouterLink>
      <button
        type="button"
        class="flex h-9 items-center gap-1.5 rounded-md px-3 text-sm text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
        @click="logout"
      >
        <LogOut class="h-4 w-4" />
        {{ t('exercises.logout') }}
      </button>
    </template>

    <div class="mb-6">
      <h1 class="text-2xl font-semibold tracking-tight">{{ t('exercises.title') }}</h1>
      <p class="mt-1 text-sm text-zinc-500">{{ t('exercises.subtitle') }}</p>
    </div>

    <div
      v-if="error"
      class="alert-error mb-4 flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-400"
    >
      <TriangleAlert class="h-4 w-4 shrink-0" />
      <span>{{ error }}</span>
    </div>

    <div v-if="loading" class="flex justify-center py-16 text-zinc-500">
      <Activity class="h-5 w-5 animate-spin" />
    </div>

    <div v-else-if="exercises.length" class="grid gap-3">
      <div
        v-for="ex in exercises"
        :key="ex.id"
        data-test="exercise-card"
        class="group flex items-center gap-5 rounded-xl border border-zinc-200 bg-white p-5 transition hover:border-indigo-400 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-indigo-500"
        :class="statusStyle[ex.status].dim"
      >
        <div
          class="flex h-11 w-11 items-center justify-center rounded-lg"
          :class="statusStyle[ex.status].tile"
        >
          <component :is="statusStyle[ex.status].icon" class="h-5 w-5" />
        </div>
        <div class="flex-1">
          <div class="mb-1 flex items-center gap-2">
            <span
              class="rounded px-2 py-0.5 text-xs font-medium"
              :class="statusStyle[ex.status].pill"
            >
              {{ t(`exercises.status.${ex.status}`) }}
            </span>
          </div>
          <div class="font-semibold">{{ ex.name }}</div>
          <div v-if="ex.description" class="mt-1 text-sm text-zinc-500">{{ ex.description }}</div>
        </div>
        <ArrowRight
          class="h-4 w-4 text-zinc-400 transition group-hover:translate-x-0.5 group-hover:text-indigo-500"
        />
      </div>
    </div>

    <div v-else data-test="empty" class="py-16 text-center text-zinc-500">
      <p>{{ t('exercises.empty') }}</p>
    </div>
  </AppShell>
</template>
