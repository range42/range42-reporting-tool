<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Plus, Upload, TriangleAlert } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import AppShell from '@/components/AppShell.vue'
import {
  listTemplates,
  createTemplate,
  importTemplate,
  type TemplateSummary,
  type TemplateBundle,
} from '@/services/templates'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const templates = ref<TemplateSummary[]>([])
const error = ref('')
const fileInput = ref<HTMLInputElement | null>(null)

const token = computed(() => auth.token ?? '')

onMounted(async () => {
  if (!auth.token) return
  try {
    templates.value = await listTemplates(token.value)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Failed to load templates'
  }
})

async function handleNew(): Promise<void> {
  error.value = ''
  try {
    const created = await createTemplate(token.value, { name: 'Untitled', report_type: 'custom' })
    await router.push('/settings/templates/' + created.id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Failed to create template'
  }
}

function triggerImport(): void {
  fileInput.value?.click()
}

async function handleImport(event: Event): Promise<void> {
  error.value = ''
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const text = await file.text()
    const bundle: TemplateBundle = JSON.parse(text)
    const detail = await importTemplate(token.value, bundle)
    await router.push('/settings/templates/' + detail.id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Failed to import template'
  } finally {
    if (fileInput.value) fileInput.value.value = ''
  }
}

const statusBadge: Record<string, string> = {
  draft: 'bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300',
  published: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300',
  archived: 'bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300',
}
</script>

<template>
  <AppShell :title="t('templates.title')">
    <template #actions>
      <input
        ref="fileInput"
        type="file"
        accept=".json,application/json"
        class="hidden"
        @change="handleImport"
      />
      <button
        type="button"
        class="flex h-9 items-center gap-1.5 rounded-md border border-zinc-200 px-3 text-sm text-zinc-600 transition hover:bg-zinc-100 dark:border-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-800"
        @click="triggerImport"
      >
        <Upload class="h-4 w-4" />
        {{ t('templates.import') }}
      </button>
      <button
        type="button"
        data-test="new"
        class="flex h-9 items-center gap-1.5 rounded-md bg-indigo-500 px-3 text-sm font-medium text-white transition hover:bg-indigo-400"
        @click="handleNew"
      >
        <Plus class="h-4 w-4" />
        {{ t('templates.new') }}
      </button>
    </template>

    <div class="mb-6">
      <h1 class="text-2xl font-semibold tracking-tight">{{ t('templates.title') }}</h1>
      <p class="mt-1 text-sm text-zinc-500">{{ t('templates.subtitle') }}</p>
    </div>

    <div
      v-if="error"
      class="alert-error mb-4 flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-400"
    >
      <TriangleAlert class="h-4 w-4 shrink-0" />
      <span>{{ error }}</span>
    </div>

    <div
      class="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900"
    >
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-zinc-200 text-left dark:border-zinc-800">
            <th class="px-5 py-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
              {{ t('templates.name') }}
            </th>
            <th class="px-5 py-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
              {{ t('templates.reportType') }}
            </th>
            <th class="px-5 py-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
              {{ t('templates.sections') }}
            </th>
            <th class="px-5 py-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
              Status
            </th>
            <th class="px-5 py-3 text-xs font-medium uppercase tracking-wider text-zinc-500">v</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="tpl in templates"
            :key="tpl.id"
            data-test="template-row"
            :class="[
              'cursor-pointer border-b border-zinc-100 last:border-0 transition hover:bg-zinc-50 dark:border-zinc-800/60 dark:hover:bg-zinc-800/40',
              tpl.status === 'archived' ? 'opacity-60' : '',
            ]"
            @click="router.push('/settings/templates/' + tpl.id)"
          >
            <td class="px-5 py-3 font-medium">{{ tpl.name }}</td>
            <td class="px-5 py-3 text-zinc-500">
              <code class="text-xs">{{ tpl.report_type }}</code>
            </td>
            <td class="px-5 py-3 text-zinc-500">{{ tpl.section_count }}</td>
            <td class="px-5 py-3">
              <span
                :class="[
                  'rounded px-1.5 py-0.5 text-[11px] font-medium',
                  statusBadge[tpl.status] ?? statusBadge['draft'],
                ]"
              >
                {{ tpl.status }}
              </span>
            </td>
            <td class="px-5 py-3 text-zinc-400">{{ tpl.version }}</td>
          </tr>
          <tr v-if="templates.length === 0">
            <td colspan="5" class="px-5 py-8 text-center text-sm text-zinc-400">
              <span data-test="empty">{{ t('templates.empty') }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </AppShell>
</template>
