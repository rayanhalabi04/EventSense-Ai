import { api } from './api'
import type { Task, CreateTaskRequest, UpdateTaskRequest, TaskStatus } from '../types'

export const tasksService = {
  list: async (filters?: { status?: TaskStatus; conversation_id?: string }): Promise<Task[]> => {
    const res = await api.get<Task[]>('/api/v1/tasks', { params: filters })
    return res.data
  },

  get: async (id: string): Promise<Task> => {
    const res = await api.get<Task>(`/api/v1/tasks/${id}`)
    return res.data
  },

  create: async (data: CreateTaskRequest): Promise<Task> => {
    const res = await api.post<Task>('/api/v1/tasks', data)
    return res.data
  },

  update: async (id: string, data: UpdateTaskRequest): Promise<Task> => {
    const res = await api.patch<Task>(`/api/v1/tasks/${id}`, data)
    return res.data
  },
}
