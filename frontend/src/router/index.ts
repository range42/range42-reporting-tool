import { createRouter, createWebHistory } from 'vue-router'
import Boot from '@/views/Boot.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [{ path: '/', component: Boot }],
})
