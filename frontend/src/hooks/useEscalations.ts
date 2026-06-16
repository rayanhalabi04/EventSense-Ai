import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { escalationsService } from '../services/escalations'
import type { EscalationStatus, UpdateEscalationRequest } from '../types'

export function useEscalations(filters?: { status?: EscalationStatus; conversation_id?: string }) {
  return useQuery({
    queryKey: ['escalations', filters],
    queryFn: () => escalationsService.list(filters),
  })
}

export function useUpdateEscalation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateEscalationRequest }) =>
      escalationsService.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['escalations'] }),
  })
}
