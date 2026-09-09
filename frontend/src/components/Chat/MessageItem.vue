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
      <div v-if="msg.isThinking && elapsedMs !== null" class="response-duration">
        耗时 {{ formatDuration(elapsedMs) }}
      </div>
      
      <!-- Actual response text -->
      <template v-else>
        <MessageContent
          :text="msg.text"
          :is-user="false"
          :msg-index="msgIndex"
          @cite-click="onCiteClick"
        />

        <div v-if="elapsedMs !== null" class="response-duration">
          耗时 {{ formatDuration(elapsedMs) }}
        </div>

        <!-- Utility actions (copy / regenerate) -->
        <div v-if="msg.text" class="msg-actions">
          <button class="msg-action-btn" :class="{ copied }" title="复制" type="button" @click="copyMessage">
            <i :class="copied ? 'icon-check' : 'icon-copy'" aria-hidden="true"></i>
          </button>
          <button class="msg-action-btn" title="重新生成" type="button">
            <i class="icon-rotate-ccw" aria-hidden="true"></i>
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
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
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
const now = ref(Date.now());
let timerId: number | null = null;

const isTiming = computed(
  () => !props.msg.isUser && props.msg.startedAt !== undefined && props.msg.durationMs === undefined,
);

const elapsedMs = computed<number | null>(() => {
  if (props.msg.durationMs !== undefined) return props.msg.durationMs;
  if (props.msg.startedAt !== undefined) return Math.max(0, now.value - props.msg.startedAt);
  return null;
});

const formatDuration = (durationMs: number) => {
  const totalSeconds = durationMs / 1000;
  if (totalSeconds < 60) return `${totalSeconds.toFixed(1)} 秒`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.floor(totalSeconds % 60);
  return `${minutes} 分 ${seconds} 秒`;
};

const stopTimer = () => {
  if (timerId !== null) {
    window.clearInterval(timerId);
    timerId = null;
  }
};

const syncTimer = (timing: boolean) => {
  stopTimer();
  if (timing) {
    now.value = Date.now();
    timerId = window.setInterval(() => {
      now.value = Date.now();
    }, 100);
  }
};

onMounted(() => syncTimer(isTiming.value));
watch(isTiming, syncTimer);
onBeforeUnmount(stopTimer);

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
