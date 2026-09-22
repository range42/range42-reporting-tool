<script setup lang="ts">
/**
 * Global-Admin screen: define a campaign as a set of report specs, fanned out per team.
 *
 * Each spec becomes one report PER TEAM in the exercise (n specs x m teams) — there is no team
 * or evaluator picker here. Evaluators are resolved automatically from the team- and
 * campaign-evaluator assignments made on the two sibling screens, once a fanned-out report is
 * submitted.
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Plus, Trash2 } from '@lucide/vue'
import AppShell from '@/components/AppShell.vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import { listTemplates, type TemplateSummary } from '@/services/templates'
import { createCampaign, type CampaignReportSpec } from '@/services/campaigns'

interface SpecRow {
  templateId: string
  availableLocal: string
  dueLocal: string
}

const inputClass =
  'h-10 w-full rounded-md border border-zinc-200 bg-white px-3 outline-none transition focus:border-indigo-400 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const exerciseId = String(route.params.exerciseId)
const token = computed(() => auth.token ?? '')

const templates = ref<TemplateSummary[]>([])
const name = ref('')
const specs = ref<SpecRow[]>([{ templateId: '', availableLocal: '', dueLocal: '' }])
const error = ref('')
const saving = ref(false)

const canSubmit = computed(
  () =>
    name.value.trim() !== '' &&
    specs.value.length > 0 &&
    specs.value.every((s) => s.templateId !== '') &&
    !saving.value,
)

function addSpec(): void {
  specs.value.push({ templateId: '', availableLocal: '', dueLocal: '' })
}

function removeSpec(index: number): void {
  specs.value.splice(index, 1)
}

onMounted(async () => {
  if (!auth.token) return
  try {
    templates.value = await listTemplates(token.value, 'published')
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('campaigns.define.loadError')
  }
})

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  error.value = ''
  saving.value = true
  try {
    const reportSpecs: CampaignReportSpec[] = specs.value.map((s) => ({
      template_id: s.templateId,
      available_at: s.availableLocal ? new Date(s.availableLocal).toISOString() : null,
      due_at: s.dueLocal ? new Date(s.dueLocal).toISOString() : null,
    }))
    const created = await createCampaign(token.value, exerciseId, {
      name: name.value.trim(),
      report_specs: reportSpecs,
    })
    await router.push(`/exercises/${exerciseId}/campaigns/${created.id}/evaluators`)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('campaigns.define.createError')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppShell :title="t('campaigns.define.title')">
    <div class="mb-6">
      <h1 class="text-2xl font-semibold tracking-tight">{{ t('campaigns.define.title') }}</h1>
      <p class="mt-1 text-sm text-zinc-500">{{ t('campaigns.define.subtitle') }}</p>
    </div>

    <form class="space-y-6" data-test="define-form" @submit.prevent="submit">
      <div>
        <label class="mb-1 block text-xs text-zinc-500">{{ t('campaigns.define.name') }}</label>
        <input v-model="name" data-test="define-name" :class="inputClass" />
      </div>

      <div class="space-y-3">
        <h2 class="text-xs font-medium uppercase tracking-wider text-zinc-500">
          {{ t('campaigns.define.specsHeading') }}
        </h2>

        <div
          v-for="(spec, i) in specs"
          :key="i"
          :data-test="`spec-row-${i}`"
          class="grid grid-cols-1 gap-3 rounded-lg border border-zinc-200 p-3 sm:grid-cols-[2fr_1fr_1fr_auto] dark:border-zinc-800"
        >
          <div>
            <label class="mb-1 block text-xs text-zinc-500">{{
              t('campaigns.define.template')
            }}</label>
            <select :data-test="`spec-template-${i}`" v-model="spec.templateId" :class="inputClass">
              <option value="">{{ t('campaigns.define.templatePlaceholder') }}</option>
              <option v-for="tpl in templates" :key="tpl.id" :value="tpl.id">{{ tpl.name }}</option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-xs text-zinc-500">{{
              t('campaigns.define.availableAt')
            }}</label>
            <input
              :data-test="`spec-available-${i}`"
              v-model="spec.availableLocal"
              type="datetime-local"
              :class="inputClass"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs text-zinc-500">{{
              t('campaigns.define.dueAt')
            }}</label>
            <input
              :data-test="`spec-due-${i}`"
              v-model="spec.dueLocal"
              type="datetime-local"
              :class="inputClass"
            />
          </div>
          <div class="flex items-end">
            <button
              type="button"
              :data-test="`remove-spec-${i}`"
              :disabled="specs.length <= 1"
              class="flex h-10 items-center gap-1 rounded-md px-2 text-xs text-red-500 transition hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-40"
              @click="removeSpec(i)"
            >
              <Trash2 class="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        <button
          type="button"
          data-test="add-spec"
          class="flex h-9 items-center gap-1.5 rounded-md border border-zinc-200 px-3 text-sm text-zinc-600 transition hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
          @click="addSpec"
        >
          <Plus class="h-4 w-4" />
          {{ t('campaigns.define.addSpec') }}
        </button>
      </div>

      <p v-if="error" data-test="define-error" class="text-sm text-red-500">{{ error }}</p>

      <button
        type="submit"
        data-test="define-submit"
        :disabled="!canSubmit"
        class="flex h-10 items-center rounded-md bg-indigo-500 px-4 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:opacity-50"
      >
        {{ t('campaigns.define.submit') }}
      </button>
    </form>
  </AppShell>
</template>
