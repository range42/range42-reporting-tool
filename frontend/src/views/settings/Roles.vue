<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/services/http'
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
  catalogue.value = await listPermissions(token.value)
  await reload()
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
</script>

<template>
  <main class="p-8">
    <header class="flex items-start justify-between mb-8">
      <div>
        <h1 class="text-3xl font-bold">{{ t('roles.title') }}</h1>
        <p class="text-base-content/60">{{ t('roles.subtitle') }}</p>
      </div>
      <div class="flex gap-2">
        <RouterLink to="/exercises" class="btn btn-ghost btn-sm">{{ t('roles.back') }}</RouterLink>
        <button class="btn btn-primary btn-sm" data-test="create" @click="openCreate">
          {{ t('roles.create') }}
        </button>
      </div>
    </header>

    <div v-if="error" class="alert alert-error mb-4">
      <span>{{ error }}</span>
    </div>

    <div class="card bg-base-100 shadow-md">
      <div class="card-body overflow-x-auto">
        <table class="table table-zebra">
          <thead>
            <tr>
              <th>{{ t('roles.label') }}</th>
              <th>{{ t('roles.key') }}</th>
              <th>{{ t('roles.permissions') }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="role in roles" :key="role.id" :data-test="`role-row-${role.id}`">
              <td>
                {{ role.display_label }}
                <span v-if="role.is_system" class="badge badge-ghost badge-sm ml-2">{{
                  t('roles.system')
                }}</span>
              </td>
              <td>
                <code class="text-xs">{{ role.role_key }}</code>
              </td>
              <td>
                <div class="flex flex-wrap gap-1">
                  <span v-for="p in role.permissions" :key="p" class="badge badge-sm">{{ p }}</span>
                </div>
              </td>
              <td class="flex gap-2 justify-end">
                <button
                  class="btn btn-ghost btn-xs"
                  data-test="edit"
                  :disabled="role.is_system"
                  @click="openEdit(role)"
                >
                  {{ t('roles.edit') }}
                </button>
                <button
                  class="btn btn-ghost btn-xs text-error"
                  data-test="delete"
                  :disabled="role.is_system"
                  @click="remove(role)"
                >
                  {{ t('roles.delete') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="modalOpen" class="modal modal-open">
      <div class="modal-box max-w-lg">
        <form data-test="save-form" @submit.prevent="save">
          <h3 class="font-semibold text-lg mb-4">
            {{ editing ? t('roles.edit') : t('roles.create') }}
          </h3>
          <div class="space-y-3">
            <div class="form-control">
              <label class="label"
                ><span class="label-text">{{ t('roles.key') }}</span></label
              >
              <input
                v-model="form.role_key"
                data-test="role_key"
                class="input input-bordered"
                :disabled="!!editing"
              />
            </div>
            <div class="form-control">
              <label class="label"
                ><span class="label-text">{{ t('roles.label') }}</span></label
              >
              <input
                v-model="form.display_label"
                data-test="display_label"
                class="input input-bordered"
              />
            </div>
            <div class="form-control">
              <label class="label"
                ><span class="label-text">{{ t('roles.description') }}</span></label
              >
              <textarea
                v-model="form.description"
                class="textarea textarea-bordered"
                rows="2"
              ></textarea>
            </div>
            <div class="form-control">
              <label class="label"
                ><span class="label-text">{{ t('roles.permissions') }}</span></label
              >
              <div class="grid grid-cols-1 gap-1 max-h-60 overflow-y-auto">
                <label
                  v-for="perm in catalogue"
                  :key="perm"
                  class="label cursor-pointer justify-start gap-2"
                >
                  <input
                    type="checkbox"
                    class="checkbox checkbox-sm checkbox-primary"
                    :value="perm"
                    v-model="form.permissions"
                  />
                  <span class="label-text">{{ perm }}</span>
                </label>
              </div>
            </div>
          </div>
          <div class="modal-action">
            <button type="button" class="btn btn-ghost" @click="modalOpen = false">
              {{ t('roles.cancel') }}
            </button>
            <button type="submit" class="btn btn-primary" data-test="save">
              {{ t('roles.save') }}
            </button>
          </div>
        </form>
      </div>
      <div class="modal-backdrop" @click="modalOpen = false"></div>
    </div>
  </main>
</template>
