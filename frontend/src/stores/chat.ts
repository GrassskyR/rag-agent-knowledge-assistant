import { defineStore } from 'pinia';
import { markRaw } from 'vue';
import { useAuthStore } from './auth';
import { useSessionStore } from './sessions';
import api from '@/utils/api';
import type { Message, RagStep, GroupedRagStep, QueuedMessage, ConversationState, ChatRequestState } from '@/types/chat';

const createConversation = (loaded = true): ConversationState => ({
  messages: [],
  userInput: '',
  pendingImages: [],
  webSearchEnabled: false,
  queue: [],
  pauseReason: null,
  request: null,
  isGenerating: false,
  loaded,
  historyLoading: false,
});

const createSessionId = () => 'session_' + crypto.randomUUID();

export const useChatStore = defineStore('chat', {
  state: () => {
    const sessionId = createSessionId();
    return {
      conversations: { [sessionId]: createConversation() } as Record<string, ConversationState>,
      sessionId,
      activeNav: 'newChat' as 'newChat' | 'history' | 'settings',
    };
  },

  getters: {
    currentSession: (state): ConversationState => state.conversations[state.sessionId],
    messages(): Message[] {
      return this.currentSession.messages;
    },
    isLoading(): boolean {
      return this.currentSession.request !== null;
    },
  },

  actions: {
    appendRagStepToGroups(prev: GroupedRagStep[], step: RagStep): GroupedRagStep[] {
      const groups = prev ? [...prev] : [];
      const g = step.group || null;
      
      if (g) {
        const idx = groups.findIndex((grp) => grp.group === g);
        if (idx >= 0) {
          const existing = groups[idx];
          const updated: GroupedRagStep = {
            group: existing.group,
            label: existing.label,
            steps: [...existing.steps, step],
            collapsed: existing.collapsed,
          };
          groups[idx] = updated;
          return groups;
        }
        return [...groups, { group: g, label: g, steps: [step], collapsed: true }];
      }

      const last = groups.length > 0 ? groups[groups.length - 1] : null;
      if (last && last.group === null) {
        const updated = { ...last, steps: [...last.steps, step] };
        groups[groups.length - 1] = updated;
        return groups;
      }
      return [...groups, { group: null, label: null, steps: [step], collapsed: false }];
    },

    groupRagSteps(steps: RagStep[]): GroupedRagStep[] {
      if (!steps || !steps.length) return [];
      return steps.reduce((groups: GroupedRagStep[], step) => this.appendRagStepToGroups(groups, step), []);
    },

    toggleStepGroup(msgIndex: number, groupIndex: number) {
      const msg = this.messages[msgIndex];
      if (!msg || !msg._groupedSteps || !msg._groupedSteps[groupIndex]) return;
      msg._groupedSteps[groupIndex].collapsed = !msg._groupedSteps[groupIndex].collapsed;
    },

    handleNewChat() {
      const sessionId = createSessionId();
      this.conversations[sessionId] = createConversation();
      this.sessionId = sessionId;
      this.activeNav = 'newChat';
      useSessionStore().showHistorySidebar = false;
    },

    async handleClearChat() {
      if (!confirm('确定要清空当前对话吗？')) return;
      await this.discardSession(this.sessionId);
    },

    async discardSession(sessionId: string) {
      const conversation = this.conversations[sessionId];
      if (conversation) {
        conversation.queue = [];
        conversation.pauseReason = 'interrupted';
        const request = conversation.request;
        if (request) {
          request.stopped = true;
          request.controller.abort();
          await request.completion;
        }
        delete this.conversations[sessionId];
      }
      if (this.sessionId === sessionId) this.handleNewChat();
    },

    resetConversations() {
      for (const conversation of Object.values(this.conversations)) {
        conversation.queue = [];
        conversation.pauseReason = 'interrupted';
        if (conversation.request) {
          conversation.request.stopped = true;
          conversation.request.controller.abort();
        }
      }
      const sessionId = createSessionId();
      this.conversations = { [sessionId]: createConversation() };
      this.sessionId = sessionId;
      this.activeNav = 'newChat';
      const sessionStore = useSessionStore();
      sessionStore.sessions = [];
      sessionStore.showHistorySidebar = false;
    },

    async loadSession(sessionId: string) {
      if (!this.conversations[sessionId]) {
        this.conversations[sessionId] = createConversation(false);
      }
      const conversation = this.conversations[sessionId];
      this.sessionId = sessionId;
      this.activeNav = 'newChat';
      useSessionStore().showHistorySidebar = false;
      if (conversation.loaded || conversation.historyLoading) return;

      conversation.historyLoading = true;
      try {
        const response = await api.get('/sessions/' + encodeURIComponent(sessionId));
        if (this.conversations[sessionId] !== conversation) return;
        conversation.messages = (response.data.messages || []).map((msg: any, index: number) => ({
          id: sessionId + '-history-' + index,
          text: msg.content,
          isUser: msg.type === 'human',
          durationMs: msg.type === 'ai' ? msg.rag_trace?.duration_ms ?? undefined : undefined,
          ragTrace: msg.rag_trace?.tool_used ? msg.rag_trace : null,
        }));
        conversation.loaded = true;
      } catch (error: any) {
        if (this.conversations[sessionId] !== conversation) return;
        throw new Error(error.response?.data?.detail || error.message || '加载会话失败');
      } finally {
        conversation.historyLoading = false;
        this.processQueue(sessionId);
      }
    },

    handleStop() {
      const conversation = this.currentSession;
      const request = conversation.request;
      if (!request || !conversation.isGenerating) return;
      conversation.pauseReason = 'interrupted';
      request.stopped = true;
      request.controller.abort();
    },

    resumeQueue() {
      this.currentSession.pauseReason = null;
      this.processQueue(this.sessionId);
    },

    removeQueuedMessage(id: string) {
      this.currentSession.queue = this.currentSession.queue.filter(item => item.id !== id);
    },

    handleSend() {
      if (!useAuthStore().isAuthenticated) {
        alert('请先登录');
        return;
      }
      const conversation = this.currentSession;
      const text = conversation.userInput.trim();
      if (!text && !conversation.pendingImages.length) return;
      conversation.queue.push({
        id: crypto.randomUUID(),
        text,
        images: [...conversation.pendingImages],
        webSearchEnabled: conversation.webSearchEnabled,
      });
      conversation.userInput = '';
      conversation.pendingImages = [];
      this.processQueue(this.sessionId);
    },

    processQueue(sessionId: string) {
      const conversation = this.conversations[sessionId];
      if (!conversation || !conversation.loaded || conversation.request || conversation.pauseReason) return;
      if (!useAuthStore().isAuthenticated) return;
      const nextMessage = conversation.queue.shift();
      if (!nextMessage) return;
      const request = markRaw<ChatRequestState>({
        controller: new AbortController(),
        stopped: false,
        completion: Promise.resolve(),
      });
      conversation.request = request;
      conversation.isGenerating = true;
      request.completion = this.sendQueuedMessage(sessionId, conversation, nextMessage, request);
    },

    async sendQueuedMessage(
      sessionId: string,
      conversation: ConversationState,
      queued: QueuedMessage,
      request: ChatRequestState,
    ) {
      const authStore = useAuthStore();
      const sessionStore = useSessionStore();
      conversation.messages.push({
        id: queued.id,
        text: queued.text,
        isUser: true,
        images: queued.images.length ? queued.images : undefined,
      });
      if (!sessionStore.sessions.some(item => item.session_id === sessionId)) {
        sessionStore.sessions.unshift({
          session_id: sessionId,
          title: queued.text ? queued.text.slice(0, 10) + (queued.text.length > 10 ? '...' : '') : '图片对话',
          message_count: conversation.messages.length,
          updated_at: new Date().toISOString(),
        });
      }
      conversation.messages.push({
        id: crypto.randomUUID(),
        text: '',
        isUser: false,
        isThinking: true,
        startedAt: Date.now(),
        ragTrace: null,
        ragSteps: [],
        _groupedSteps: [],
      });
      // 保留本次请求所属消息的引用，切换会话不会改变流式写入目标。
      const botMessage = conversation.messages[conversation.messages.length - 1];
      let completed = false;
      let failed = false;
      let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;

      try {
        const response = await fetch('/chat/stream', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: 'Bearer ' + authStore.token,
          },
          body: JSON.stringify({
            message: queued.text,
            session_id: sessionId,
            images: queued.images.length ? queued.images : undefined,
            web_search_enabled: queued.webSearchEnabled,
          }),
          signal: request.controller.signal,
        });
        if (!response.ok) {
          if (response.status === 401) {
            authStore.handleLogout();
            throw new Error('登录已过期，请重新登录');
          }
          throw new Error('HTTP ' + response.status);
        }

        reader = response.body?.getReader();
        if (!reader) throw new Error('无法读取响应流');
        const decoder = new TextDecoder();
        let buffer = '';

        while (!completed) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          buffer = buffer.replace(/\r\n/g, '\n');
          let eventEndIndex;
          while ((eventEndIndex = buffer.indexOf('\n\n')) !== -1) {
            const eventStr = buffer.slice(0, eventEndIndex);
            buffer = buffer.slice(eventEndIndex + 2);
            const dataStr = eventStr.split('\n')
              .filter(line => line.startsWith('data:'))
              .map(line => line.slice(5).trimStart()).join('\n');
            if (!dataStr) continue;
            if (dataStr === '[DONE]') {
              completed = true;
              break;
            }
            const data = JSON.parse(dataStr);
            if (request.stopped) continue;
            if (data.type === 'content') {
              botMessage.isThinking = false;
              botMessage.text += data.content;
            } else if (data.type === 'trace') {
              botMessage.ragTrace = data.rag_trace?.tool_used ? data.rag_trace : null;
            } else if (data.type === 'response_complete') {
              botMessage.isThinking = false;
              botMessage.durationMs = data.duration_ms;
              conversation.isGenerating = false;
            } else if (data.type === 'rag_step') {
              botMessage.ragSteps!.push(data.step);
              botMessage._groupedSteps = this.appendRagStepToGroups(botMessage._groupedSteps || [], data.step);
            } else if (data.type === 'session_title') {
              const session = sessionStore.sessions.find(item => item.session_id === sessionId);
              if (session) session.title = data.title;
            } else if (data.type === 'error') {
              failed = true;
              botMessage.isThinking = false;
              botMessage.text += '\n\n抱歉，出了点问题：' + data.content;
              conversation.pauseReason = 'error';
            }
          }
        }
        if (!completed && !failed && !request.stopped) throw new Error('回答连接已断开');
      } catch (error: any) {
        if (request.stopped || error.name === 'AbortError') {
          botMessage.text = botMessage.text
            ? botMessage.text + '\n\n_(回答已被终止)_'
            : '(已终止回答)';
        } else {
          failed = true;
          conversation.pauseReason = 'error';
          botMessage.text += '\n\n抱歉，出了点问题：' + error.message;
        }
      } finally {
        reader?.releaseLock();
        botMessage.isThinking = false;
        botMessage.durationMs ??= Math.max(0, Date.now() - botMessage.startedAt!);
        if (conversation.request === request) {
          conversation.request = null;
          conversation.isGenerating = false;
        }
        if (this.conversations[sessionId] === conversation) {
          const session = sessionStore.sessions.find(item => item.session_id === sessionId);
          if (session) {
            session.message_count = conversation.messages.length;
            session.updated_at = new Date().toISOString();
          }
          this.processQueue(sessionId);
        }
      }
    },
  },
});
