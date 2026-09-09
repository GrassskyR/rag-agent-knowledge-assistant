<template>
  <div class="input-area-wrapper">
    <section v-if="conversation.queue.length" class="message-queue" aria-label="待发送消息">
      <div class="message-queue-header">
        <span>待发送 {{ conversation.queue.length }}</span>
        <button v-if="conversation.pauseReason" type="button" class="queue-resume" @click="chatStore.resumeQueue">继续</button>
      </div>
      <p v-if="conversation.pauseReason" class="message-queue-notice" role="status">
        {{ conversation.pauseReason === 'interrupted'
          ? '由于你中断了消息回复，队列已暂停，按 Enter 发送队列中首条消息'
          : '上一条消息未完成，队列已暂停，按 Enter 发送队列中首条消息' }}
      </p>
      <ol class="message-queue-viewport">
        <li v-for="(message, index) in conversation.queue" :key="message.id" class="message-queue-item">
          <span class="queue-position">{{ index + 1 }}.</span>
          <div class="queue-message">
            <span class="queue-message-text">{{ message.text || '图片消息' }}</span>
            <span v-if="message.images.length" class="queue-image-count">{{ message.images.length }} 张图片</span>
          </div>
          <button type="button" class="queue-remove" title="移除排队消息" aria-label="移除排队消息" @click="chatStore.removeQueuedMessage(message.id)">
            <i class="icon-x" aria-hidden="true"></i>
          </button>
        </li>
      </ol>
    </section>

    <!-- Floating, pill-shaped input container -->
    <div class="input-area">
      <!-- Image attachment previews -->
      <div v-if="conversation.pendingImages.length" class="image-previews">
        <div v-for="(img, idx) in conversation.pendingImages" :key="idx" class="image-preview">
          <img :src="img" alt="待上传图片" />
          <button class="image-preview-remove" type="button" title="移除" @click="removeImage(idx)">
            <i class="icon-x" aria-hidden="true"></i>
          </button>
        </div>
      </div>

      <textarea
        v-model="conversation.userInput"
        @keydown="handleKeyDown"
        @compositionstart="handleCompositionStart"
        @compositionend="handleCompositionEnd"
        @input="autoResize"
        :placeholder="conversation.pendingImages.length ? '为图片添加说明（可选）... (Shift+Enter 换行)' : '输入消息... (Shift+Enter 换行)'"
        rows="1"
        ref="textareaRef"
      ></textarea>

      <div class="input-actions">
        <!-- Action chips (visual placeholders) -->
        <div class="action-chips">
          <button class="action-chip" type="button" title="上传图片" @click="triggerFileInput">
            <i class="icon-image" aria-hidden="true"></i> 图片
          </button>
          <button
            class="action-chip"
            :class="{ active: conversation.webSearchEnabled }"
            type="button"
            title="联网搜索"
            @click="toggleWebSearch"
          >
            <i class="icon-search" aria-hidden="true"></i> 搜索
          </button>
        </div>

        <div class="input-send-actions">
          <button
            v-if="conversation.isGenerating"
            @click="chatStore.handleStop"
            class="send-btn stop-btn"
            type="button"
            title="终止当前回答"
            aria-label="终止当前回答"
          >
            <i class="icon-square" aria-hidden="true"></i>
          </button>
          <button
            @click="onSend"
            class="send-btn"
            type="button"
            :disabled="!hasDraft && !canResume"
            :title="chatStore.isLoading ? '加入发送队列' : '发送'"
            :aria-label="chatStore.isLoading ? '加入发送队列' : '发送'"
          >
            <i class="icon-arrow-up" aria-hidden="true"></i>
          </button>
        </div>
      </div>
      <input
        ref="fileInputRef"
        type="file"
        accept="image/*"
        multiple
        class="hidden-file-input"
        @change="onFilesSelected"
      />
    </div>
    <div class="footer-text">AI 生成的内容可能包含错误，请仔细甄别。</div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, nextTick } from 'vue';
import { useChatStore } from '@/stores/chat';

const chatStore = useChatStore();
const conversation = chatStore.currentSession;
const hasDraft = computed(() => !!conversation.userInput.trim() || !!conversation.pendingImages.length);
const canResume = computed(() => !!conversation.pauseReason && !!conversation.queue.length);
const textareaRef = ref<HTMLTextAreaElement | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);
const isComposing = ref(false);

const MAX_IMAGES = 4;
const MAX_IMAGE_SIZE = 5 * 1024 * 1024;

const triggerFileInput = () => {
  fileInputRef.value?.click();
};

const onFilesSelected = (event: Event) => {
  const input = event.target as HTMLInputElement;
  const files = input.files;
  if (!files) return;
  void addFiles(Array.from(files));
  input.value = '';
};

const addFiles = (files: File[]) => {
  for (const file of files) {
    if (conversation.pendingImages.length >= MAX_IMAGES) {
      alert(`最多上传 ${MAX_IMAGES} 张图片`);
      break;
    }
    if (!file.type.startsWith('image/')) {
      alert('仅支持图片文件');
      continue;
    }
    if (file.size > MAX_IMAGE_SIZE) {
      alert('单张图片不能超过 5MB');
      continue;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result === 'string') {
        conversation.pendingImages.push(result);
      }
    };
    reader.readAsDataURL(file);
  }
};

const removeImage = (idx: number) => {
  conversation.pendingImages.splice(idx, 1);
};

const toggleWebSearch = () => {
  conversation.webSearchEnabled = !conversation.webSearchEnabled;
};

const handleCompositionStart = () => {
  isComposing.value = true;
};

const handleCompositionEnd = () => {
  isComposing.value = false;
};

const handleKeyDown = (event: KeyboardEvent) => {
  if (event.key === 'Enter' && !event.shiftKey && !isComposing.value) {
    event.preventDefault();
    if (canResume.value) {
      chatStore.resumeQueue();
    } else {
      onSend();
    }
  }
};

const autoResize = () => {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto';
    textareaRef.value.style.height = textareaRef.value.scrollHeight + 'px';
  }
};

const resetTextareaHeight = () => {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto';
  }
};

const onSend = async () => {
  if (isComposing.value) return;
  if (hasDraft.value) {
    chatStore.handleSend();
  } else if (canResume.value) {
    chatStore.resumeQueue();
  }
  await nextTick();
  resetTextareaHeight();
};

onMounted(autoResize);
</script>
