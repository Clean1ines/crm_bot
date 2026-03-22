import { components } from '@/shared/api/generated/schema'; // путь до твоего сгенерированного файла

export type Project = components['schemas']['ProjectResponse'];
export type ProjectCreate = components['schemas']['ProjectCreate'];
export type ProjectUpdate = components['schemas']['ProjectUpdate'];