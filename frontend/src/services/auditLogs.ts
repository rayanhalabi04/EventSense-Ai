import { api } from './api'
import type { AuditLog } from '../types'

export const auditLogsService = {
  list: async (params?: { limit?: number; offset?: number }): Promise<AuditLog[]> => {
    const res = await api.get<AuditLog[]>('/api/v1/audit-logs', { params })
    return res.data
  },
}
