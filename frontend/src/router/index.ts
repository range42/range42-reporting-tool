import { createRouter, createWebHistory } from 'vue-router'
import { resolveNavigation, type RouteFlags } from '@/router/guards'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/exercises' },
    {
      path: '/login',
      component: () => import('@/views/Login.vue'),
      meta: { public: true, loginPage: true },
    },
    {
      path: '/auth/callback',
      component: () => import('@/views/AuthCallback.vue'),
      meta: { public: true },
    },
    {
      path: '/exercises',
      component: () => import('@/views/ExercisePicker.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/settings/roles',
      component: () => import('@/views/settings/Roles.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
  ],
})

router.beforeEach((to) => resolveNavigation(to.meta as RouteFlags, to.path) ?? true)
