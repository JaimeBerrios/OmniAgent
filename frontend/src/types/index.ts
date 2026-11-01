export interface Customer { id: number; tenant_id: number; external_id: string; name: string | null; created_at: string }
export interface Conversation { id: number; tenant_id: number; customer_id: number; channel: string; status: string; created_at: string }
export interface Message { id: number; tenant_id: number; conversation_id: number; direction: 'inbound' | 'outbound'; content: string; created_at: string }
export interface Profile { id: number; email: string; is_active: boolean }
export interface Tenant { tenant_id: number; organization: string; role: string }
