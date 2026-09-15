import ts from '@vue/eslint-config-typescript'
export default [
  { ignores: ['dist/**', 'node_modules/**', 'coverage/**', 'src/types/api.d.ts'] },
  ...ts(),
]
