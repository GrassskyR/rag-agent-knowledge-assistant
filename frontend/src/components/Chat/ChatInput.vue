<template>
  <div class="input-area-wrapper">
    <!-- Floating, pill-shaped input container -->
    <div class="input-area">
      <!-- Image attachment previews -->
      <div v-if="chatStore.pendingImages.length" class="image-previews">
        <div v-for="(img, idx) in chatStore.pendingImages" :key="idx" class="image-preview">
          <img :src="img" alt="待上传图片" />
          <button class="image-preview-remove" type="button" title="移除" @click="removeImage(idx)">
            <i class="fas fa-xmark"></i>
          </button>
        </div>
      </div>

      <textarea
        v-model="chatStore.userInput"
        @keydown="handleKeyDown"
        @compositionstart="handleCompositionStart"
        @compositionend="handleCompositionEnd"
        @input="autoResize"
        :placeholder="chatStore.pendingImages.length ? '为图片添加说明（可选）... (Shift+Enter 换行)' : '输入消息... (Shift+Enter 换行)'"
        rows="1"
        ref="textareaRef"
      ></textarea>

      <div class="input-actions">
        <!-- Action chips (visual placeholders) -->
        <div class="action-chips">
          <button class="action-chip" type="button" title="上传图片" @click="triggerFileInput">
            <i class="fas fa-image"></i> 图片
          </button>
          <button
            class="action-chip"
            :class="{ active: chatStore.activeNav === 'tasks' }"
            type="button"
            title="任务清单"
            @click="toggleTasks"
          >
            <i class="fas fa-list-check"></i> 任务
          </button>
          <button
            class="action-chip"
            :class="{ active: chatStore.webSearchEnabled }"
            type="button"
            title="联网搜索"
            @click="toggleWebSearch"
          >
            <i class="fas fa-magnifying-glass"></i> 搜索
          </button>
        </div>

        <button
          v-if="chatStore.isLoading"
          @click="chatStore.handleStop"
          class="send-btn stop-btn"
          title="终止回答"
        >
          <i class="fas fa-stop"></i>
        </button>

        <button
          v-else
          @click="onSend"
          class="send-btn"
          title="发送"
        >
          <i class="fas fa-arrow-up"></i>
        </button>
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
import { ref, nextTick } from 'vue';
import { useChatStore } from '@/stores/chat';
import { useSessionStore } from '@/stores/sessions';

const chatStore = useChatStore();
const sessionStore = useSessionStore();
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
    if (chatStore.pendingImages.length >= MAX_IMAGES) {
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
        chatStore.pendingImages.push(result);
      }
    };
    reader.readAsDataURL(file);
  }
};

const removeImage = (idx: number) => {
  chatStore.pendingImages.splice(idx, 1);
};

const toggleTasks = () => {
  if (chatStore.activeNav === 'tasks') {
    chatStore.activeNav = 'newChat';
  } else {
    chatStore.activeNav = 'tasks';
    sessionStore.showHistorySidebar = false;
  }
};

const toggleWebSearch = () => {
  chatStore.webSearchEnabled = !chatStore.webSearchEnabled;
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
    onSend();
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
  const text = chatStore.userInput.trim();
  if ((!text && chatStore.pendingImages.length === 0) || chatStore.isLoading || isComposing.value) return;

  await chatStore.handleSend();

  await nextTick();
  resetTextareaHeight();
};
</script>
