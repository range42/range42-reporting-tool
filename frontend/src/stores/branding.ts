import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet } from '@/services/http'

interface BrandingConfig {
  app_name: string
  logo_url: string
  primary_color: string
}

const DEFAULTS: BrandingConfig = {
  app_name: 'Reporting Tool',
  logo_url: '',
  primary_color: '#2563eb',
}

export const useBrandingStore = defineStore('branding', () => {
  const appName = ref(DEFAULTS.app_name)
  const logoUrl = ref(DEFAULTS.logo_url)
  const primaryColor = ref(DEFAULTS.primary_color)

  function apply(cfg: BrandingConfig): void {
    appName.value = cfg.app_name
    logoUrl.value = cfg.logo_url
    primaryColor.value = cfg.primary_color
    document.title = cfg.app_name
    document.documentElement.style.setProperty('--rt-primary', cfg.primary_color)
  }

  async function load(): Promise<void> {
    try {
      apply(await apiGet<BrandingConfig>('/api/v1/config'))
    } catch {
      apply(DEFAULTS)
    }
  }

  return { appName, logoUrl, primaryColor, load }
})
