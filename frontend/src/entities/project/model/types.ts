export interface Project {
  id: string;
  name: string;
  is_pro_mode: boolean;
  template_slug: string | null;
  managers: number[];
  user_id: string | null;
  client_bot_username?: string | null;
  manager_bot_username?: string | null;
}
