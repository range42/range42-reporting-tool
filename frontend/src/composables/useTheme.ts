import { ref } from 'vue'

const STORAGE_KEY = 'rt-theme'
const isDark = ref(true)

function applyTheme(dark: boolean): void {
  isDark.value = dark
  document.documentElement.classList.toggle('dark', dark)
}

/** Dark/light theme, default dark, persisted in localStorage (mirrors the mockup). */
export function useTheme() {
  function init(): void {
    const saved = localStorage.getItem(STORAGE_KEY)
    applyTheme(saved ? saved === 'dark' : true)
  }
  function toggle(): void {
    const dark = !isDark.value
    localStorage.setItem(STORAGE_KEY, dark ? 'dark' : 'light')
    applyTheme(dark)
  }
  return { isDark, init, toggle }
}
