<template>
  <div :class="['message', msg.isUser ? 'user-message' : 'bot-message']">
    <!-- User or finished AI answer -->
    <template v-if="msg.isUser">
      <div v-if="msg.images && msg.images.length" class="message-images">
        <a
          v-for="(img, idx) in msg.images"
          :key="idx"
          :href="img"
          target="_blank"
          rel="noopener"
          class="message-image-thumb"
        >
          <img :src="img" alt="用户上传图片" />
        </a>
      </div>
      <MessageContent 
        :text="msg.text" 
        :is-user="true" 
        :msg-index="msgIndex" 
      />
    </template>
    
    <template v-else>
      <!-- RAG Thinking/Trace view -->
      <ThinkingTrace 
        v-if="msg.isThinking && !msg.text" 
        :msg="msg" 
        :msg-index="msgIndex" 
      />
      
      <!-- Actual response text -->
      <template v-else>
        <MessageContent
          :text="msg.text"
          :is-user="false"
          :msg-index="msgIndex"
          @cite-click="onCiteClick"
        />

        <!-- Utility actions (copy / regenerate) -->
        <div v-if="msg.text" class="msg-actions">
          <button class="msg-action-btn" :class="{ copied }" title="复制" type="button" @click="copyMessage">
            <i :class="copied ? 'fas fa-check' : 'fas fa-copy'"></i>
          </button>
          <button class="msg-action-btn" title="重新生成" type="button">
            <i class="fas fa-rotate-right"></i>
          </button>
        </div>

        <!-- RAG Source documents -->
        <References 
          ref="referencesRef"
          :msg="msg" 
          :msg-index="msgIndex" 
          @cite-click="onCiteClick"
        />
        
        <!-- Deep retrieval traces logs -->
        <RetrievalTraceDetails :msg="msg" />
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import MessageContent from './MessageContent.vue';
import ThinkingTrace from './ThinkingTrace.vue';
import References from './References.vue';
import RetrievalTraceDetails from './RetrievalTraceDetails.vue';
import type { Message } from '@/types/chat';

const props = defineProps<{
  msg: Message;
  msgIndex: number;
}>();

const emit = defineEmits<{
  (e: 'cite-click', msgIndex: number, chunkIndex: number): void;
}>();

const referencesRef = ref<InstanceType<typeof References> | null>(null);
const copied = ref(false);

const copyMessage = async () => {
  try {
    await navigator.clipboard.writeText(props.msg.text);
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 1500);
  } catch (_) {
    // clipboard unavailable — ignore
  }
};

const openReferences = () => {
  referencesRef.value?.openDetails();
};

defineExpose({
  openReferences
});

const onCiteClick = (msgIndex: number, chunkIndex: number) => {
  emit('cite-click', msgIndex, chunkIndex);
};
</script>
