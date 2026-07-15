<template>
  <div class="task-panel">
    <div class="task-header">
      <h2><i class="fas fa-list-check"></i> 任务清单</h2>
      <p>AI 在对话中自动提取的可执行待办，勾选标记完成</p>
    </div>

    <div v-if="taskStore.loading" class="task-loading">加载中...</div>

    <template v-else>
      <div v-if="activeTodos.length" class="task-section">
        <div class="task-section-title">待办 ({{ activeTodos.length }})</div>
        <ul class="task-list">
          <li v-for="todo in activeTodos" :key="todo.id" class="task-item">
            <label class="task-check">
              <input type="checkbox" @change="taskStore.toggleTodo(todo.id)" />
              <span class="task-text">{{ todo.text }}</span>
            </label>
            <button class="task-delete" type="button" title="删除" @click="taskStore.deleteTodo(todo.id)">
              <i class="fas fa-trash-alt"></i>
            </button>
          </li>
        </ul>
      </div>

      <div v-if="doneTodos.length" class="task-section">
        <div class="task-section-title">
          已完成 ({{ doneTodos.length }})
          <button class="task-clear-btn" type="button" @click="taskStore.clearDone">清空已完成</button>
        </div>
        <ul class="task-list">
          <li v-for="todo in doneTodos" :key="todo.id" class="task-item done">
            <label class="task-check">
              <input type="checkbox" checked @change="taskStore.toggleTodo(todo.id)" />
              <span class="task-text">{{ todo.text }}</span>
            </label>
            <button class="task-delete" type="button" title="删除" @click="taskStore.deleteTodo(todo.id)">
              <i class="fas fa-trash-alt"></i>
            </button>
          </li>
        </ul>
      </div>

      <div v-if="!activeTodos.length && !doneTodos.length" class="task-empty">
        <i class="fas fa-clipboard-list"></i>
        <p>当前会话暂无任务</p>
        <p class="task-empty-hint">在对话中提到需要做的事，AI 会自动提取到这里</p>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue';
import { useTaskStore } from '@/stores/tasks';
import { useChatStore } from '@/stores/chat';

const taskStore = useTaskStore();
const chatStore = useChatStore();

const activeTodos = computed(() => taskStore.todos.filter((t) => !t.done));
const doneTodos = computed(() => taskStore.todos.filter((t) => t.done));

const load = () => {
  if (chatStore.sessionId) {
    void taskStore.loadTodos(chatStore.sessionId);
  }
};

onMounted(load);
watch(() => chatStore.sessionId, load);
</script>
