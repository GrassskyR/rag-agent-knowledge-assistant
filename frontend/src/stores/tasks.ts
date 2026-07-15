import { defineStore } from 'pinia';
import api from '@/utils/api';

export interface TodoItem {
  id: string;
  text: string;
  done: boolean;
  created_at: string;
}

export const useTaskStore = defineStore('tasks', {
  state: () => ({
    todos: [] as TodoItem[],
    loading: false,
    sessionId: '' as string,
  }),

  actions: {
    async loadTodos(sessionId: string) {
      this.sessionId = sessionId;
      this.loading = true;
      try {
        const resp = await api.get(`/sessions/${encodeURIComponent(sessionId)}/todos`);
        this.todos = resp.data.todos || [];
      } catch (e: any) {
        this.todos = [];
      } finally {
        this.loading = false;
      }
    },

    async saveTodos() {
      try {
        const resp = await api.patch(
          `/sessions/${encodeURIComponent(this.sessionId)}/todos`,
          { todos: this.todos }
        );
        this.todos = resp.data.todos || [];
      } catch (e: any) {
        // save failure is non-blocking
      }
    },

    toggleTodo(id: string) {
      const t = this.todos.find((x) => x.id === id);
      if (t) {
        t.done = !t.done;
        void this.saveTodos();
      }
    },

    deleteTodo(id: string) {
      this.todos = this.todos.filter((x) => x.id !== id);
      void this.saveTodos();
    },

    clearDone() {
      this.todos = this.todos.filter((x) => !x.done);
      void this.saveTodos();
    },
  },
});
