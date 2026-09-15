<template>
  <div 
    v-if="sources.length"
    class="references-section"
  >
    <details class="references-details" ref="detailsRef">
      <summary class="references-title"><i class="icon-book" aria-hidden="true"></i> 参考文献</summary>
      <ul class="sources-list references-list">
        <li
          v-for="(chunk, cIdx) in sources"
          :key="cIdx"
          class="source-item"
          :id="`chunk-${msgIndex}-${cIdx + 1}`"
        >
          <div class="source-title-line">
            <span 
              class="ref-index cite-ref" 
              :data-msg-index="msgIndex" 
              :data-chunk-index="cIdx + 1"
              @click="onCiteClick(cIdx + 1)"
            >[{{ cIdx + 1 }}]</span>
            <a
              v-if="chunk.url"
              class="source-file source-link"
              :href="chunk.url"
              target="_blank"
              rel="noopener noreferrer"
            >
              {{ chunk.title || chunk.filename || chunk.url }}
            </a>
            <button
              v-else-if="isPdfSource(chunk)"
              class="source-file source-link document-link"
              type="button"
              :disabled="openingFilename === chunk.filename"
              @click="openDocument(chunk)"
            >
              {{ chunk.filename }}
            </button>
            <span v-else class="source-file">{{ chunk.filename }}</span>
            <span v-if="chunk.page_number" class="source-page"> - 第 {{ chunk.page_number }} 页</span>
          </div>
          <div class="source-meta-line">
            <span class="source-page">
              {{ chunk.source_type === 'web' ? '搜索名次' : 'RRF名次' }}：#{{ chunk.rrf_rank || (cIdx + 1) }}
            </span>
            <span v-if="chunk.engine" class="source-page">引擎：{{ chunk.engine }}</span>
            <span v-if="chunk.fetched" class="source-page">已读取正文</span>
            <span v-if="chunk.rerank_score !== null && chunk.rerank_score !== undefined" class="source-page">
              Rerank分数：{{ Number(chunk.rerank_score).toFixed(4) }}
            </span>
          </div>
          <div v-if="chunk.text" class="source-excerpt">{{ chunk.text }}</div>
        </li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import api from '@/utils/api';
import { useAuthStore } from '@/stores/auth';
import type { Message } from '@/types/chat';

const props = defineProps<{
  msg: Message;
  msgIndex: number;
}>();

const emit = defineEmits<{
  (e: 'cite-click', msgIndex: number, chunkIndex: number): void;
}>();

const detailsRef = ref<HTMLDetailsElement | null>(null);
const openingFilename = ref<string | null>(null);
const authStore = useAuthStore();
const sources = computed(() => {
  const trace = props.msg.ragTrace;
  if (!trace) return [];
  if (trace.web_sources && trace.web_sources.length) return trace.web_sources;
  return trace.retrieved_chunks || [];
});

const openDetails = () => {
  if (detailsRef.value) {
    detailsRef.value.open = true;
  }
};

const onCiteClick = (chunkIndex: number) => {
  emit('cite-click', props.msgIndex, chunkIndex);
};

const isPdfSource = (chunk: (typeof sources.value)[number]) => {
  return chunk.source_type !== 'web' && /\.pdf$/i.test(chunk.filename || '');
};

const openDocumentAt = async (chunkIndex: number) => {
  const chunk = sources.value[chunkIndex - 1];
  if (!chunk || !isPdfSource(chunk)) return false;
  await openDocument(chunk);
  return true;
};

const openDocument = async (chunk: (typeof sources.value)[number]) => {
  if (!authStore.isAuthenticated || !authStore.token) {
    alert('请先登录');
    return;
  }

  const popup = window.open('about:blank', '_blank');
  if (!popup) {
    alert('请允许弹出窗口后重试');
    return;
  }

  openingFilename.value = chunk.filename;
  try {
    const response = await api.get(`/documents/file/${encodeURIComponent(chunk.filename)}`, {
      responseType: 'blob',
    });
    const blobUrl = URL.createObjectURL(response.data);
    const rawPage = Number(chunk.page_number);
    const page = Number.isFinite(rawPage) ? Math.max(rawPage + 1, 1) : 1;
    popup.location.href = `${blobUrl}#page=${page}`;
  } catch (error: any) {
    popup.close();
    alert(error.response?.data?.detail || '文档打开失败');
  } finally {
    openingFilename.value = null;
  }
};

defineExpose({
  openDetails,
  openDocumentAt,
});
</script>
