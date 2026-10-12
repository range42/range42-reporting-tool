<script setup lang="ts">
/**
 * Global-Admin list screen: every campaign in the exercise. Links out to the existing create
 * form (`campaign-define`) and to each campaign's detail hub (`campaign-detail`), and offers
 * delete in place.
 */
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Plus, TriangleAlert, Trash2 } from '@lucide/vue'
import AppShell from '@/components/AppShell.vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import { deleteCampaign, listCampaigns, type Campaign } from '@/services/campaigns'

const { t } = useI18n()
const route = useRoute()
const auth = useAuthStore()

const exerciseId = String(route.params.exerciseId)
const token = computed(() => auth.token ?? '')

const campaigns = ref<Campaign[]>([])
const loading = ref(true)
const error = ref('')
const deleteErrors = ref<Record<string, string>>({})

async function load(): Promise<void> {
  campaigns.value = await listCampaigns(token.value, exerciseId)
}

onMounted(async () => {
  if (!auth.token) {
    loading.value = false
    return
  }
  try {
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('campaigns.manage.loadError')
  }
  loading.value = false
})

async function remove(c: Campaign): Promise<void> {
  if (!window.confirm(t('campaigns.manage.deleteConfirm'))) return
  delete deleteErrors.value[c.id]
  try {
    await deleteCampaign(token.value, exerciseId, c.id)
    campaigns.value = campaigns.value.filter((row) => row.id !== c.id)
  } catch (e) {
    deleteErrors.value = {
      ...deleteErrors.value,
      [c.id]: e instanceof ApiError ? e.message : t('campaigns.manage.deleteError'),
    }
  }
}
</script>

<template>
  <AppShell :title="t('campaigns.manage.title')">
    <template #actions>
      <RouterLink
        :to="`/exercises/${exerciseId}/campaigns/new`"
        data-test="new-campaign-link"
        class="flex h-9 items-center gap-1.5 rounded-md bg-indigo-500 px-3 text-sm font-medium text-white transition hover:bg-indigo-400"
      >
        <Plus class="h-4 w-4" />
        {{ t('campaigns.new') }}
      </RouterLink>
    </template>

    <div class="mb-6">
      <h1 class="text-2xl font-semibold tracking-tight">{{ t('campaigns.manage.title') }}</h1>
      <p class="mt-1 text-sm text-zinc-500">{{ t('campaigns.manage.subtitle') }}</p>
    </div>

    <div
      v-if="error"
      data-test="campaigns-load-error"
      class="mb-4 flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-400"
    >
      <TriangleAlert class="h-4 w-4 shrink-0" />
      <span>{{ error }}</span>
    </div>

    <template v-else-if="!loading">
      <p v-if="campaigns.length === 0" data-test="campaigns-empty" class="text-sm text-zinc-500">
        {{ t('campaigns.manage.empty') }}
      </p>

      <ul v-else class="space-y-2">
        <li
          v-for="c in campaigns"
          :key="c.id"
          :data-test="`campaign-row-${c.id}`"
          class="rounded-lg border border-zinc-200 px-4 py-3 dark:border-zinc-800"
        >
          <div class="flex items-center justify-between gap-3">
            <RouterLink
              :to="`/exercises/${exerciseId}/campaigns/${c.id}`"
              :data-test="`campaign-link-${c.id}`"
              class="min-w-0 flex-1"
            >
              <p class="truncate text-sm font-medium">{{ c.name }}</p>
              <p class="text-xs text-zinc-500">
                {{ t('campaigns.manage.reportsCount', { count: c.report_count }) }}
              </p>
            </RouterLink>
            <button
              type="button"
              :data-test="`delete-campaign-${c.id}`"
              class="flex h-8 items-center gap-1 rounded-md px-2 text-xs text-red-500 transition hover:bg-red-500/10"
              @click="remove(c)"
            >
              <Trash2 class="h-3.5 w-3.5" />
              {{ t('campaigns.manage.deleteAction') }}
            </button>
          </div>
          <p
            v-if="deleteErrors[c.id]"
            :data-test="`delete-campaign-error-${c.id}`"
            class="mt-2 text-xs text-red-500"
          >
            {{ deleteErrors[c.id] }}
          </p>
        </li>
      </ul>
    </template>
  </AppShell>
</template>
