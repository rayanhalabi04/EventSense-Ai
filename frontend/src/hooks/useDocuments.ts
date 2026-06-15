import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { documentsService } from '../services/documents'
import type { DocumentFilters } from '../types'

export function useDocuments(filters?: DocumentFilters) {
  return useQuery({
    queryKey: ['documents', filters],
    queryFn: () => documentsService.list(filters),
  })
}

export function useUploadDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ file, document_type, title }: { file: File; document_type: string; title?: string }) =>
      documentsService.upload(file, document_type, title),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  })
}

export function useArchiveDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => documentsService.archive(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  })
}
