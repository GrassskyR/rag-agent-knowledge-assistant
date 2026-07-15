<template>
  <div 
    v-if="sources.length"
    class="references-section"
  >
    <details class="references-details" ref="detailsRef">
      <summary class="references-title"><i class="fas fa-book"></i> 参考文献</summary>
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
import type { Message } from '@/types/chat';

const props = defineProps<{
  msg: Message;
  msgIndex: number;
}>();

const emit = defineEmits<{
  (e: 'cite-click', msgIndex: number, chunkIndex: number): void;
}>();

const detailsRef = ref<HTMLDetailsElement | null>(null);
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

defineExpose({
  openDetails
});

const onCiteClick = (chunkIndex: number) => {
  emit('cite-click', props.msgIndex, chunkIndex);
};
</script>
