import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),

  // Основные правила для всех TS/TSX файлов
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
  },

  // Специальные правила для тестовых файлов (ослабляем требования)
  {
    files: ['**/*.test.{ts,tsx}', '**/test/**/*.{ts,tsx}', 'src/app/test/setup.ts'],
    rules: {
      // Разрешаем explicit any в тестах
      '@typescript-eslint/no-explicit-any': 'off',
      // Отключаем проверки unsafe, так как в тестах мы часто обращаемся к мокам
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
      '@typescript-eslint/no-unsafe-call': 'off',
      // (опционально) Разрешаем неиспользуемые переменные, если они нужны для моков
      '@typescript-eslint/no-unused-vars': 'off',
    },
  },
])
