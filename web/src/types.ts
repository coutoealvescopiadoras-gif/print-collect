export interface Client {
  id: number;
  partner_id?: number | null;
  name: string;
  cnpj: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  address: string | null;
  active: boolean;
  created_at: string;
}

export interface Printer {
  id: number;
  client_id: number;
  location_id: number | null;
  ip_address: string;
  serial_number: string | null;
  model: string | null;
  manufacturer: string | null;
  status: string;
  pages_total: number;
  pages_bw: number;
  pages_color: number;
  toner_black: number | null;
  toner_cyan: number | null;
  toner_magenta: number | null;
  toner_yellow: number | null;
  last_seen: string | null;
}

export interface Location {
  id: number;
  client_id: number;
  name: string;
  sector: string | null;
  responsible: string | null;
  address: string | null;
}

export interface Alert {
  id: number;
  printer_id: number;
  alert_type: string;
  message: string;
  severity: string;
  resolved: boolean;
  created_at: string;
}

export interface Agent {
  id: number;
  client_id: number;
  name: string;
  api_token: string;
  last_heartbeat: string | null;
  version: string | null;
  active: boolean;
  created_at?: string;
  hostname?: string | null;
  remote_ip?: string | null;
  pairing_code?: string | null;
  pairing_expires_at?: string | null;
  paired_at?: string | null;
}

export interface AgentPairingCode {
  agent_id: number;
  client_id: number;
  name: string;
  pairing_code: string;
  pairing_expires_at: string;
  server_url?: string | null;
}

export interface DashboardStats {
  total_clients: number;
  total_printers: number;
  online_printers: number;
  offline_printers: number;
  active_alerts: number;
  low_toner_count: number;
}

export interface Partner {
  id: number;
  name: string;
  logo_url: string | null;
  active: boolean;
  created_at: string;
}

export interface PartnerBillingStats {
  partner_id: number;
  partner_name: string;
  total_clients: number;
  total_printers: number;
  billable_printers: number;
  online_printers: number;
  offline_printers: number;
}

export interface User {
  id: number;
  username: string;
  email: string;
  role: "superadmin" | "partner_admin" | "client_manager" | "client_viewer";
  client_id: number | null;
  partner_id?: number | null;
  active: boolean;
  created_at: string;
}
