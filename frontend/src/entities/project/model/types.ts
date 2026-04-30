export interface Project {
  id: string;
  name: string;
  is_pro_mode: boolean;
  user_id: string | null;
  client_bot_username?: string | null;
  manager_bot_username?: string | null;
  access_role?: string | null;
}
