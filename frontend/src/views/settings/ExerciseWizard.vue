<script setup lang="ts">
/** Global-Admin screen: create an exercise. Lands on its settings screen once created. */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/AppShell.vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import { createExercise } from '@/services/exercises'

const inputClass =
  'h-10 w-full rounded-md border border-zinc-200 bg-white px-3 outline-none transition focus:border-indigo-400 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

const name = ref('')
const description = ref('')
const startsLocal = ref('')
const endsLocal = ref('')
const classification = ref('')
const tlp = ref('')
const error = ref('')
const saving = ref(false)

const canSubmit = computed(() => name.value.trim() !== '' && !saving.value)

async function submit(): Promise<void> {
  if (!canSubmit.value || !auth.token) return
  error.value = ''
  saving.value = true
  try {
    const created = await createExercise(auth.token, {
      name: name.value.trim(),
      description: description.value.trim() || null,
      starts_at: startsLocal.value ? new Date(startsLocal.value).toISOString() : null,
      ends_at: endsLocal.value ? new Date(endsLocal.value).toISOString() : null,
      classification: classification.value.trim() || null,
      tlp: tlp.value.trim() || null,
    })
    await router.push(`/exercises/${created.id}/settings`)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('exercises.wizard.createError')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppShell :title="t('exercises.wizard.title')">
    <div class="mx-auto max-w-2xl">
      <div class="mb-6">
        <h1 class="text-2xl font-semibold tracking-tight">{{ t('exercises.wizard.title') }}</h1>
        <p class="mt-1 text-sm text-zinc-500">{{ t('exercises.wizard.subtitle') }}</p>
      </div>

      <form
        data-test="wizard-form"
        class="space-y-5 rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900"
        @submit.prevent="submit"
      >
        <div>
          <label class="mb-1 block text-xs font-medium text-zinc-500">{{
            t('exercises.wizard.name')
          }}</label>
          <input v-model="name" data-test="wizard-name" :class="inputClass" />
        </div>

        <div>
          <label class="mb-1 block text-xs font-medium text-zinc-500">{{
            t('exercises.wizard.description')
          }}</label>
          <textarea v-model="description" rows="2" :class="inputClass" />
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="mb-1 block text-xs font-medium text-zinc-500">{{
              t('exercises.wizard.starts')
            }}</label>
            <input
              v-model="startsLocal"
              data-test="wizard-starts"
              type="datetime-local"
              :class="inputClass"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-zinc-500">{{
              t('exercises.wizard.ends')
            }}</label>
            <input
              v-model="endsLocal"
              data-test="wizard-ends"
              type="datetime-local"
              :class="inputClass"
            />
          </div>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="mb-1 block text-xs font-medium text-zinc-500">{{
              t('exercises.wizard.classification')
            }}</label>
            <input
              v-model="classification"
              data-test="wizard-classification"
              :placeholder="t('exercises.wizard.classificationPlaceholder')"
              :class="inputClass"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-zinc-500">{{
              t('exercises.wizard.tlp')
            }}</label>
            <input
              v-model="tlp"
              data-test="wizard-tlp"
              :placeholder="t('exercises.wizard.tlpPlaceholder')"
              :class="inputClass"
            />
          </div>
        </div>

        <p v-if="error" data-test="wizard-error" class="text-sm text-red-500">{{ error }}</p>

        <div class="flex justify-end gap-2 pt-2">
          <button
            type="button"
            class="flex h-9 items-center rounded-md border border-zinc-200 px-3 text-sm transition hover:bg-zinc-100 dark:border-zinc-800 dark:hover:bg-zinc-800"
            @click="router.push('/exercises')"
          >
            {{ t('exercises.wizard.cancel') }}
          </button>
          <button
            type="submit"
            data-test="wizard-submit"
            :disabled="!canSubmit"
            class="flex h-9 items-center rounded-md bg-indigo-500 px-4 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:opacity-50"
          >
            {{ t('exercises.wizard.submit') }}
          </button>
        </div>
      </form>
    </div>
  </AppShell>
</template>
