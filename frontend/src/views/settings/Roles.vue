<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { Plus, TriangleAlert } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
import AppShell from '@/components/AppShell.vue'
import {
  createRole,
  deleteRole,
  listPermissions,
  listRoles,
  updateRole,
  type Role,
} from '@/services/roles'

const { t } = useI18n()
const auth = useAuthStore()
const roles = ref<Role[]>([])
const catalogue = ref<string[]>([])
const error = ref('')
const modalOpen = ref(false)
const editing = ref<Role | null>(null)
const form = ref({ role_key: '', display_label: '', description: '', permissions: [] as string[] })

const token = computed(() => auth.token ?? '')

async function reload(): Promise<void> {
  roles.value = await listRoles(token.value)
}

onMounted(async () => {
  if (!auth.token) return
  try {
    catalogue.value = await listPermissions(token.value)
    await reload()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Failed to load roles'
  }
})

function openCreate(): void {
  editing.value = null
  form.value = { role_key: '', display_label: '', description: '', permissions: [] }
  error.value = ''
  modalOpen.value = true
}

function openEdit(role: Role): void {
  editing.value = role
  form.value = {
    role_key: role.role_key,
    display_label: role.display_label,
    description: role.description ?? '',
    permissions: [...role.permissions],
  }
  error.value = ''
  modalOpen.value = true
}

async function save(): Promise<void> {
  error.value = ''
  try {
    if (editing.value) {
      await updateRole(token.value, editing.value.id, {
        display_label: form.value.display_label,
        description: form.value.description || null,
        permissions: form.value.permissions,
      })
    } else {
      await createRole(token.value, {
        role_key: form.value.role_key,
        display_label: form.value.display_label,
        description: form.value.description || null,
        permissions: form.value.permissions,
      })
    }
    modalOpen.value = false
    await reload()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Save failed'
  }
}

async function remove(role: Role): Promise<void> {
  if (!window.confirm(t('roles.deleteConfirm'))) return
  error.value = ''
  try {
    await deleteRole(token.value, role.id)
    await reload()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Delete failed'
  }
}

const inputClass =
  'h-10 w-full rounded-md border border-zinc-200 bg-white px-3 outline-none transition focus:border-indigo-400 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900'
</script>

<template>
  <AppShell :title="t('roles.title')">
    <template #actions>
      <RouterLink
        to="/exercises"
        class="flex h-9 items-center rounded-md px-3 text-sm text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
      >
        {{ t('roles.back') }}
      </RouterLink>
      <button
        type="button"
        data-test="create"
        class="flex h-9 items-center gap-1.5 rounded-md bg-indigo-500 px-3 text-sm font-medium text-white transition hover:bg-indigo-400"
        @click="openCreate"
      >
        <Plus class="h-4 w-4" />
        {{ t('roles.create') }}
      </button>
    </template>

    <div class="mb-6">
      <h1 class="text-2xl font-semibold tracking-tight">{{ t('roles.title') }}</h1>
      <p class="mt-1 text-sm text-zinc-500">{{ t('roles.subtitle') }}</p>
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
              {{ t('roles.label') }}
            </th>
            <th class="px-5 py-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
              {{ t('roles.key') }}
            </th>
            <th class="px-5 py-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
              {{ t('roles.permissions') }}
            </th>
            <th class="px-5 py-3"></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="role in roles"
            :key="role.id"
            :data-test="`role-row-${role.id}`"
            class="border-b border-zinc-100 last:border-0 dark:border-zinc-800/60"
          >
            <td class="px-5 py-3">
              <span class="font-medium">{{ role.display_label }}</span>
              <span
                v-if="role.is_system"
                class="ml-2 rounded bg-zinc-200 px-1.5 py-0.5 text-[11px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
              >
                {{ t('roles.system') }}
              </span>
            </td>
            <td class="px-5 py-3">
              <code class="text-xs text-zinc-500">{{ role.role_key }}</code>
            </td>
            <td class="px-5 py-3">
              <div class="flex max-w-md flex-wrap gap-1">
                <span
                  v-for="p in role.permissions"
                  :key="p"
                  class="rounded bg-indigo-500/10 px-1.5 py-0.5 font-mono text-[11px] text-indigo-500"
                >
                  {{ p }}
                </span>
              </div>
            </td>
            <td class="px-5 py-3">
              <div class="flex justify-end gap-1">
                <button
                  type="button"
                  data-test="edit"
                  :disabled="role.is_system"
                  class="rounded-md px-2 py-1 text-xs text-zinc-600 transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-40 dark:text-zinc-300 dark:hover:bg-zinc-800"
                  @click="openEdit(role)"
                >
                  {{ t('roles.edit') }}
                </button>
                <button
                  type="button"
                  data-test="delete"
                  :disabled="role.is_system"
                  class="rounded-md px-2 py-1 text-xs text-red-500 transition hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-40"
                  @click="remove(role)"
                >
                  {{ t('roles.delete') }}
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Editor modal -->
    <div
      v-if="modalOpen"
      class="modal-open fixed inset-0 z-50 flex items-center justify-center p-4"
    >
      <div class="absolute inset-0 bg-black/50" @click="modalOpen = false"></div>
      <div
        class="relative z-10 w-full max-w-lg rounded-xl border border-zinc-200 bg-white p-6 shadow-xl dark:border-zinc-800 dark:bg-zinc-900"
      >
        <form data-test="save-form" @submit.prevent="save">
          <h3 class="mb-4 text-lg font-semibold tracking-tight">
            {{ editing ? t('roles.edit') : t('roles.create') }}
          </h3>
          <div class="space-y-4">
            <div>
              <label class="mb-1 block text-xs text-zinc-500">{{ t('roles.key') }}</label>
              <input
                v-model="form.role_key"
                data-test="role_key"
                :disabled="!!editing"
                :class="inputClass"
              />
            </div>
            <div>
              <label class="mb-1 block text-xs text-zinc-500">{{ t('roles.label') }}</label>
              <input v-model="form.display_label" data-test="display_label" :class="inputClass" />
            </div>
            <div>
              <label class="mb-1 block text-xs text-zinc-500">{{ t('roles.description') }}</label>
              <textarea
                v-model="form.description"
                rows="2"
                class="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-900"
              ></textarea>
            </div>
            <div>
              <label class="mb-1 block text-xs text-zinc-500">{{ t('roles.permissions') }}</label>
              <div
                class="grid max-h-60 grid-cols-1 gap-0.5 overflow-y-auto rounded-md border border-zinc-200 p-2 dark:border-zinc-800"
              >
                <label
                  v-for="perm in catalogue"
                  :key="perm"
                  class="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                >
                  <input
                    type="checkbox"
                    :value="perm"
                    v-model="form.permissions"
                    class="h-4 w-4 rounded border-zinc-300 text-indigo-500 accent-indigo-500 dark:border-zinc-600"
                  />
                  <span class="font-mono text-xs text-zinc-600 dark:text-zinc-300">{{ perm }}</span>
                </label>
              </div>
            </div>
          </div>
          <div class="mt-6 flex justify-end gap-2">
            <button
              type="button"
              class="flex h-9 items-center rounded-md px-3 text-sm text-zinc-500 transition hover:bg-zinc-100 dark:hover:bg-zinc-800"
              @click="modalOpen = false"
            >
              {{ t('roles.cancel') }}
            </button>
            <button
              type="submit"
              data-test="save"
              class="flex h-9 items-center rounded-md bg-indigo-500 px-4 text-sm font-medium text-white transition hover:bg-indigo-400"
            >
              {{ t('roles.save') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </AppShell>
</template>
