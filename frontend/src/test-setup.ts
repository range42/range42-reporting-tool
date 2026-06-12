/**
 * Vitest global setup: installs a fully-functional in-memory localStorage/sessionStorage
 * when the runtime environment does not provide a complete Web Storage implementation.
 * (Node 25 ships --localstorage-file which can replace the jsdom Storage with an
 * incomplete stub; this guard restores the standard API.)
 */
import { beforeEach, vi } from 'vitest'

function makeStorage(): Storage {
  let store: Record<string, string> = {}
  return {
    get length() {
      return Object.keys(store).length
    },
    key(index: number): string | null {
      const k = Object.keys(store)[index]
      return k !== undefined ? k : null
    },
    getItem(key: string): string | null {
      return Object.prototype.hasOwnProperty.call(store, key) ? (store[key] as string) : null
    },
    setItem(key: string, value: string): void {
      store[key] = String(value)
    },
    removeItem(key: string): void {
      delete store[key]
    },
    clear(): void {
      store = {}
    },
  }
}

if (typeof localStorage === 'undefined' || typeof localStorage.setItem !== 'function') {
  vi.stubGlobal('localStorage', makeStorage())
  vi.stubGlobal('sessionStorage', makeStorage())
}

beforeEach(() => {
  // Reset storage between tests regardless of implementation source
  if (typeof localStorage.clear === 'function') {
    localStorage.clear()
  }
})
