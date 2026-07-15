<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <h2>生活助手</h2>
    </div>

    <!-- New Chat — ghost button -->
    <button @click="onNewChat" class="new-chat-btn">
      <i class="fas fa-plus"></i> 新建会话
    </button>

    <!-- Navigation -->
    <nav class="sidebar-nav">
      <button @click="onHistory" :class="['nav-btn', { active: chatStore.activeNav === 'history' }]">
        <i class="fas fa-history"></i> 历史记录
      </button>
      <button @click="onTasks" :class="['nav-btn', { active: chatStore.activeNav === 'tasks' }]">
        <i class="fas fa-list-check"></i> 任务清单
      </button>
      <button v-if="authStore.isAdmin" @click="onSettings" :class="['nav-btn', { active: chatStore.activeNav === 'settings' }]">
        <i class="fas fa-cog"></i> 设置
      </button>
    </nav>

    <!-- Footer -->
    <div class="sidebar-footer">
      <div v-if="authStore.isAuthenticated" class="user-badge">
        <span>{{ authStore.currentUser?.username }}</span>
        <small>{{ authStore.currentUser?.role }}</small>
      </div>
      <button @click="chatStore.handleClearChat" class="danger-btn">
        <i class="fas fa-trash-alt"></i> 清空当前对话
      </button>
      <button v-if="authStore.isAuthenticated" @click="authStore.handleLogout" class="danger-btn logout-btn">
        <i class="fas fa-right-from-bracket"></i> 退出登录
      </button>
      <div class="footer-links">
        <a>关于</a>
        <a>帮助</a>
        <a>隐私</a>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { useAuthStore } from '@/stores/auth';
import { useChatStore } from '@/stores/chat';
import { useSessionStore } from '@/stores/sessions';

const authStore = useAuthStore();
const chatStore = useChatStore();
const sessionStore = useSessionStore();

const onNewChat = () => {
  chatStore.handleNewChat();
};

const onHistory = async () => {
  chatStore.activeNav = 'history';
  sessionStore.showHistorySidebar = !sessionStore.showHistorySidebar;
  if (sessionStore.showHistorySidebar) {
    try {
      await sessionStore.fetchSessions();
    } catch (error: any) {
      alert(error.message);
    }
  }
};

const onSettings = () => {
  if (!authStore.isAdmin) {
    alert('仅管理员可访问文档管理');
    return;
  }
  chatStore.activeNav = 'settings';
  sessionStore.showHistorySidebar = false;
};

const onTasks = () => {
  chatStore.activeNav = 'tasks';
  sessionStore.showHistorySidebar = false;
};
</script>
