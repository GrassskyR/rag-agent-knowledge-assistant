<template>
  <div class="chat-area">
    <header class="chat-header">
      <!-- Model selection (visual placeholder) -->
      <button class="model-dropdown" type="button">
        生活助手 <i class="fas fa-chevron-down chev"></i>
      </button>

      <div class="header-actions">
        <a class="header-link">帮助</a>
        <button class="login-btn" type="button">{{ authStore.currentUser?.username || '登录' }}</button>
      </div>
    </header>

    <div class="chat-container" ref="chatContainerRef">
      <div class="chat-inner">
        <WelcomeScreen v-if="chatStore.messages.length === 0" />

        <!-- Messages List -->
        <MessageItem
          v-for="(msg, index) in chatStore.messages"
          :key="index"
          :msg="msg"
          :msg-index="index"
          :ref="(el) => { if (el) messageItemRefs[index] = el; }"
          @cite-click="scrollToChunk"
        />
      </div>
    </div>

    <!-- Bottom Input Area -->
    <ChatInput />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onBeforeUpdate, onMounted } from 'vue';
import WelcomeScreen from './WelcomeScreen.vue';
import MessageItem from './MessageItem.vue';
import ChatInput from './ChatInput.vue';
import { useChatStore } from '@/stores/chat';
import { useAuthStore } from '@/stores/auth';

const chatStore = useChatStore();
const authStore = useAuthStore();
const chatContainerRef = ref<HTMLDivElement | null>(null);
const messageItemRefs = ref<any[]>([]);

onBeforeUpdate(() => {
  messageItemRefs.value = [];
});

const scrollToBottom = () => {
  if (chatContainerRef.value) {
    chatContainerRef.value.scrollTop = chatContainerRef.value.scrollHeight;
  }
};

const scrollToChunk = async (msgIndex: number, chunkIndex: number) => {
  const msgItem = messageItemRefs.value[msgIndex];
  if (!msgItem) return;

  // Expand References section
  msgItem.openReferences();

  await nextTick();
  const chunkEl = document.getElementById(`chunk-${msgIndex}-${chunkIndex}`);
  if (chunkEl) {
    chunkEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    chunkEl.classList.add('highlight-chunk');
    setTimeout(() => {
      chunkEl.classList.remove('highlight-chunk');
    }, 2000);
  }
};

// Scroll to bottom when messages list changes (e.g. streaming responses)
watch(
  () => chatStore.messages,
  () => {
    nextTick(() => {
      scrollToBottom();
    });
  },
  { deep: true }
);

onMounted(() => {
  scrollToBottom();
});
</script>
