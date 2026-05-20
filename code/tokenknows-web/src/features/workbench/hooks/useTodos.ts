/**
 * useTodos · GET /api/v1/projects/:id/todos
 */

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { TodoItem } from '@/types/api'

async function fetchTodos(id: string): Promise<TodoItem[]> {
  const { data } = await api.get<TodoItem[]>(`/projects/${id}/todos`)
  return data
}

export function useTodos(id: string | null | undefined) {
  return useQuery({
    queryKey: ['projects', id, 'todos'],
    queryFn: () => fetchTodos(id as string),
    enabled: Boolean(id),
  })
}
