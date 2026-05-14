import { de } from './locales/de';
import { en } from './locales/en';
import { es } from './locales/es';
import { ru } from './locales/ru';
import {
  SUPPORTED_LOCALES,
  type SupportedLocale,
  type TranslationDictionary,
  type TranslationKey,
  type TranslationParams,
} from './types';

export {
  SUPPORTED_LOCALES,
  type SupportedLocale,
  type TranslationDictionary,
  type TranslationKey,
  type TranslationParams,
};

export const DEFAULT_LOCALE: SupportedLocale = 'ru';

const dictionaries: Record<SupportedLocale, TranslationDictionary> = {
  ru,
  en,
  de,
  es,
};

export const isSupportedLocale = (value: string): value is SupportedLocale =>
  SUPPORTED_LOCALES.includes(value as SupportedLocale);

export const normalizeLocale = (
  value: string | null | undefined,
): SupportedLocale => {
  if (!value) {
    return DEFAULT_LOCALE;
  }

  const normalized = value.toLowerCase().split('-')[0] ?? DEFAULT_LOCALE;
  return isSupportedLocale(normalized) ? normalized : DEFAULT_LOCALE;
};

const interpolate = (template: string, params?: TranslationParams): string => {
  if (!params) {
    return template;
  }

  return template.replace(/\{([a-zA-Z0-9_.-]+)\}/g, (match, key: string) => {
    const value = params[key];
    if (value === null || value === undefined) {
      return match;
    }
    return String(value);
  });
};

export const translate = (
  key: TranslationKey,
  params?: TranslationParams,
  locale: SupportedLocale = DEFAULT_LOCALE,
): string => {
  const dictionary = dictionaries[locale] ?? dictionaries[DEFAULT_LOCALE];
  const fallback = dictionaries[DEFAULT_LOCALE][key];
  return interpolate(dictionary[key] ?? fallback, params);
};

export const t = translate;

export const createTranslator =
  (locale: SupportedLocale = DEFAULT_LOCALE) =>
  (key: TranslationKey, params?: TranslationParams): string =>
    translate(key, params, locale);

export const getTranslationDictionary = (
  locale: SupportedLocale = DEFAULT_LOCALE,
): TranslationDictionary => dictionaries[locale] ?? dictionaries[DEFAULT_LOCALE];
