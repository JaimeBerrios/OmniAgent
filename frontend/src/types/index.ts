export interface Customer { id: number; tenant_id: number; external_id: string; name: string | null; created_at: string }
export interface Conversation {
  id: number
  tenant_id: number
  customer_id: number
  channel: string
  status: string
  created_at: string
  assigned_user_id?: number | null
  automation_enabled?: boolean
  pending_reply?: boolean
  unread?: boolean
  customer_name?: string | null
  customer_external_id?: string
  last_message?: string | null
  last_message_at?: string | null
}
export interface Message { id: number; tenant_id: number; conversation_id: number; direction: 'inbound' | 'outbound'; content: string; created_at: string; delivery_status?: 'pending' | 'sending' | 'sent' | 'failed' | 'unknown' | 'available' | null }
export interface Profile { id: number; email: string; is_active: boolean }
export interface Tenant { tenant_id: number; organization: string; role: string }


export interface DashboardStats {
  customers: number
  conversations: number
  open_conversations: number
  inbound_messages: number
  outbound_messages: number
}


export interface DailyActivity {
  date: string
  inbound: number
  outbound: number
}
