<script setup lang="ts">
/**
 * Global-Admin removal of an assigned evaluator.
 *
 * A reason is MANDATORY and blocked locally as well as server-side, exactly as ReopenControl
 * does it: `UnassignRequest.reason` defaults to empty so a missing body, an empty string and
 * whitespace all reach the same `reason_required` error, and refusing the submit here saves
 * the admin discovering that by round trip.
 *
 * The removal is soft — the evaluator's grades survive for a later dispute — but it
 * renormalizes the report's aggregate, so the parent reloads rather than patching locally.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { unassignEvaluator } from '@/services/evaluations'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ exerciseId: string; rid: string; evid: string }>()
const emit = defineEmits<{ unassigned: [] }>()

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
    await unassignEvaluator(auth.token, props.exerciseId, props.rid, props.evid, reason.value)
    isOpen.value = false
    reason.value = ''
    emit('unassigned')
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
      :data-test="`unassign-open-${evid}`"
      type="button"
      class="rounded-md border border-[var(--rt-border)] px-2 py-1 text-xs transition-opacity duration-150 hover:opacity-80"
      @click="isOpen = true"
    >
      {{ t('evaluations.unassign') }}
    </button>

    <div v-else class="space-y-2">
      <label :for="`unassign-reason-${evid}`" class="block text-xs font-medium">
        {{ t('evaluations.unassignReasonLabel') }}
      </label>
      <textarea
        :id="`unassign-reason-${evid}`"
        v-model="reason"
        :data-test="`unassign-reason-${evid}`"
        rows="2"
        class="w-full resize-none rounded-md border border-[var(--rt-border)] bg-[var(--rt-bg-elev)] p-2 text-xs"
      />
      <div class="flex items-center gap-2">
        <button
          :data-test="`unassign-submit-${evid}`"
          type="button"
          :disabled="!canSubmit"
          class="rounded-md bg-amber-600 px-2 py-1 text-xs text-white transition-opacity duration-150 disabled:opacity-50"
          @click="submit"
        >
          {{ t('evaluations.unassignSubmit') }}
        </button>
        <button
          :data-test="`unassign-cancel-${evid}`"
          type="button"
          class="rounded-md border border-[var(--rt-border)] px-2 py-1 text-xs"
          @click="isOpen = false"
        >
          {{ t('evaluations.reopenCancel') }}
        </button>
      </div>
      <p v-if="failed" :data-test="`unassign-error-${evid}`" class="text-xs text-red-500">
        {{ t('evaluations.unassignFailed') }}
      </p>
    </div>
  </div>
</template>
