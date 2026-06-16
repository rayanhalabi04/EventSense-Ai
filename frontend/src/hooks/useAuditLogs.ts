import { useQuery } from '@tanstack/react-query'
import { auditLogsService } from '../services/auditLogs'

export function useAuditLogs(params?: { limit?: number; offset?: number }) {
  return useQuery({
    queryKey: ['audit-logs', params],
    queryFn: () => auditLogsService.list(params),
  })
}
