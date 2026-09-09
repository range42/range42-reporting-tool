<script setup lang="ts">
/**
 * Global-Admin reopen for a finalized evaluation (W5-4).
 *
 * A reason is MANDATORY and enforced here as well as server-side: `ReopenRequest.reason`
 * defaults to empty so an absent body, an empty string and whitespace all land on the same
 * `reason_required` error, and blocking the submit locally saves the admin discovering that
 * by round trip. The reopen produces a NEW grade version rather than an in-place edit, so
 * the parent reloads afterwards instead of patching state locally.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { reopenEvaluation } from '@/services/evaluations'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ exerciseId: string; rid: string; evid: string }>()
const emit = defineEmits<{ reopened: [] }>()

const { t } = useI18n()
const auth = useAuthStore()

const isOpen = ref(false)
const reason = ref('')
const failed = ref(false)
const inFlight = ref(false)

const canSubmit = computed(() => reason.value.trim() !== '' && !inFlight.value)

async function submit(): Promise<void> {
  if (!canSubmit.value || !auth.token) return
  inFlight.value = true
  failed.value = false
  try {
    await reopenEvaluation(auth.token, props.exerciseId, props.rid, props.evid, reason.value)
    isOpen.value = false
    reason.value = ''
    emit('reopened')
  } catch {
    failed.value = true
  } finally {
    inFlight.value = false
  }
}
</script>

<template>
  <div>
    <button
      v-if="!isOpen"
      data-test="reopen-open"
      type="button"
      class="rounded-md border border-[var(--rt-border)] px-2 py-1 text-xs transition-opacity duration-150 hover:opacity-80"
      @click="isOpen = true"
    >
      {{ t('evaluations.reopen') }}
    </button>

    <div v-else class="space-y-2">
      <label for="reopen-reason-input" class="block text-xs font-medium">
        {{ t('evaluations.reopenReasonLabel') }}
      </label>
      <textarea
        id="reopen-reason-input"
        v-model="reason"
        data-test="reopen-reason"
        rows="2"
        class="w-full resize-none rounded-md border border-[var(--rt-border)] bg-[var(--rt-bg-elev)] p-2 text-xs"
      />
      <div class="flex items-center gap-2">
        <button
          data-test="reopen-submit"
          type="button"
          :disabled="!canSubmit"
          class="rounded-md bg-amber-600 px-2 py-1 text-xs text-white transition-opacity duration-150 disabled:opacity-50"
          @click="submit"
        >
          {{ t('evaluations.reopenSubmit') }}
        </button>
        <button
          data-test="reopen-cancel"
          type="button"
          class="rounded-md border border-[var(--rt-border)] px-2 py-1 text-xs"
          @click="isOpen = false"
        >
          {{ t('evaluations.reopenCancel') }}
        </button>
      </div>
      <p v-if="failed" data-test="reopen-error" class="text-xs text-red-500">
        {{ t('evaluations.reopenFailed') }}
      </p>
    </div>
  </div>
</template>
