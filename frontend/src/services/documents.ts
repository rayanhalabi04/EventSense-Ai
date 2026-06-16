import { api } from './api'
import type { Document, DocumentFilters } from '../types'

export const documentsService = {
  list: async (filters?: DocumentFilters): Promise<Document[]> => {
    const res = await api.get<Document[]>('/api/v1/documents', { params: filters })
    return res.data
  },

  get: async (id: string): Promise<Document> => {
    const res = await api.get<Document>(`/api/v1/documents/${id}`)
    return res.data
  },

  upload: async (file: File, document_type: string, title?: string): Promise<Document> => {
    const form = new FormData()
    form.append('file', file)
    form.append('document_type', document_type)
    if (title) form.append('title', title)
    const res = await api.post<Document>('/api/v1/documents/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data
  },

  archive: async (id: string): Promise<void> => {
    await api.delete(`/api/v1/documents/${id}`)
  },
}
