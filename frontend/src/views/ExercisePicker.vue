<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { listExercises, type Exercise } from '@/services/exercises'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const exercises = ref<Exercise[]>([])
const loading = ref(true)

const badgeClass: Record<Exercise['status'], string> = {
  draft: 'badge-warning',
  active: 'badge-success',
  archived: 'badge-ghost',
}

onMounted(async () => {
  if (auth.token) {
    try {
      exercises.value = await listExercises(auth.token)
    } finally {
      loading.value = false
    }
  } else {
    loading.value = false
  }
})

async function logout(): Promise<void> {
  await auth.logout()
  await router.push('/login')
}
</script>

<template>
  <main class="p-8">
    <header class="flex items-start justify-between mb-8">
      <div>
        <h1 class="text-3xl font-bold">{{ t('exercises.title') }}</h1>
        <p class="text-base-content/60">{{ t('exercises.subtitle') }}</p>
      </div>
      <div class="flex gap-2">
        <RouterLink v-if="auth.isAdmin" to="/settings/roles" class="btn btn-outline btn-sm">
          {{ t('exercises.manageRoles') }}
        </RouterLink>
        <button class="btn btn-ghost btn-sm" @click="logout">{{ t('exercises.logout') }}</button>
      </div>
    </header>

    <div v-if="loading" class="flex justify-center py-12">
      <span class="loading loading-spinner loading-lg"></span>
    </div>

    <div v-else-if="exercises.length" class="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      <div
        v-for="ex in exercises"
        :key="ex.id"
        data-test="exercise-card"
        class="card bg-base-100 shadow-md"
      >
        <div class="card-body">
          <div class="flex items-center justify-between gap-2">
            <h2 class="card-title text-lg">{{ ex.name }}</h2>
            <span class="badge" :class="badgeClass[ex.status]">{{
              t(`exercises.status.${ex.status}`)
            }}</span>
          </div>
          <p v-if="ex.description" class="text-sm text-base-content/70">{{ ex.description }}</p>
        </div>
      </div>
    </div>

    <div v-else data-test="empty" class="text-center py-16 text-base-content/50">
      <p>{{ t('exercises.empty') }}</p>
    </div>
  </main>
</template>
