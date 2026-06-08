import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from '@/App.vue'
import { router } from '@/router'
import { i18n } from '@/i18n'
import { useBrandingStore } from '@/stores/branding'
import '@/assets/main.css'

async function bootstrap(): Promise<void> {
  const app = createApp(App)
  app.use(createPinia())
  app.use(router)
  app.use(i18n)
  await useBrandingStore().load()
  app.mount('#app')
}

void bootstrap()
