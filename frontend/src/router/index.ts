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
      path: '/exercises/:exerciseId',
      name: 'exercise-entry',
      component: () => import('@/views/ExerciseEntry.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/exercises/:exerciseId/reports',
      name: 'reports',
      component: () => import('@/views/reports/ReportList.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/exercises/:exerciseId/reports/new',
      name: 'report-create',
      component: () => import('@/views/reports/ReportCreate.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/exercises/:exerciseId/reports/approvals',
      name: 'report-approvals',
      component: () => import('@/views/reports/ApproverQueue.vue'),
      meta: { requiresAuth: true, requiresApprover: true },
    },
    {
      path: '/exercises/:exerciseId/reports/:rid',
      name: 'report-editor',
      component: () => import('@/views/reports/ReportEditor.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/exercises/:exerciseId/reports/:rid/evaluators',
      name: 'report-evaluators',
      component: () => import('@/views/reports/ReportEvaluators.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/exercises/:exerciseId/evaluations',
      name: 'evaluation-queue',
      component: () => import('@/views/evaluations/EvaluationQueuePage.vue'),
      meta: { requiresAuth: true, requiresEvaluator: true },
    },
    {
      path: '/exercises/:exerciseId/reports/:rid/evaluations/:evid',
      name: 'evaluation',
      component: () => import('@/views/evaluations/SingleEvaluation.vue'),
      meta: { requiresAuth: true, requiresEvaluator: true },
    },
    {
      path: '/exercises/:exerciseId/reports/:rid/evaluations/:evid/campaign',
      name: 'evaluation-campaign',
      component: () => import('@/views/evaluations/CampaignEvaluation.vue'),
      meta: { requiresAuth: true, requiresEvaluator: true },
    },
    {
      path: '/settings/roles',
      component: () => import('@/views/settings/Roles.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/settings/templates',
      component: () => import('@/views/settings/TemplateLibrary.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/settings/templates/:id',
      component: () => import('@/views/settings/TemplateBuilder.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
  ],
})

router.beforeEach((to) => resolveNavigation(to.meta as RouteFlags, to.path) ?? true)
