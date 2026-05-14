import { describe, expect, it } from 'vitest';
import {
  DEFAULT_LOCALE,
  SUPPORTED_LOCALES,
  createTranslator,
  getTranslationDictionary,
  normalizeLocale,
  translate,
  type TranslationDictionary,
  type TranslationKey,
} from './index';

const sortedKeys = (dictionary: TranslationDictionary): TranslationKey[] =>
  (Object.keys(dictionary) as TranslationKey[]).sort();

describe('shared i18n', () => {
  it('keeps every supported locale dictionary complete', () => {
    const ruKeys = sortedKeys(getTranslationDictionary('ru'));

    for (const locale of SUPPORTED_LOCALES) {
      expect(sortedKeys(getTranslationDictionary(locale))).toEqual(ruKeys);
    }
  });

  it('normalizes regional locale tags to supported base locales', () => {
    expect(normalizeLocale('ru-RU')).toBe('ru');
    expect(normalizeLocale('en-US')).toBe('en');
    expect(normalizeLocale('de-DE')).toBe('de');
    expect(normalizeLocale('es-ES')).toBe('es');
  });

  it('falls back to the default locale for unknown or empty values', () => {
    expect(normalizeLocale(undefined)).toBe(DEFAULT_LOCALE);
    expect(normalizeLocale(null)).toBe(DEFAULT_LOCALE);
    expect(normalizeLocale('')).toBe(DEFAULT_LOCALE);
    expect(normalizeLocale('fr-FR')).toBe(DEFAULT_LOCALE);
  });

  it('translates known keys for the default locale', () => {
    expect(translate('app.loading')).toBe('Загрузка...');
    expect(translate('common.actions.save')).toBe('Сохранить');
  });

  it('translates known keys for explicit locales', () => {
    expect(translate('app.loading', undefined, 'en')).toBe('Loading...');
    expect(translate('app.loading', undefined, 'de')).toBe('Wird geladen...');
    expect(translate('app.loading', undefined, 'es')).toBe('Cargando...');
  });

  it('supports lightweight interpolation', () => {
    const t = createTranslator('ru');

    expect(t('project.create.validation.nameTooLong', { limit: 100 })).toBe(
      'Название проекта не должно быть длиннее 100 символов',
    );
  });
});
