<template>
  <div class="settings-panel">
    <div class="settings-header">
      <h2><i class="icon-settings" aria-hidden="true"></i> 文档管理</h2>
    </div>

    <!-- Upload Section -->
    <UploadSection />

    <!-- Documents List Section -->
    <div class="documents-section">
      <h3><i class="icon-list" aria-hidden="true"></i> 已上传文档</h3>
      <button @click="onRefresh" class="btn-secondary" :disabled="documentStore.documentsLoading">
        <i class="icon-refresh-cw" :class="{ 'icon-spin': documentStore.documentsLoading }" aria-hidden="true"></i> 刷新列表
      </button>
      
      <div v-if="documentStore.documentsLoading" class="loading-indicator">
        加载中...
      </div>
      
      <div v-else-if="documentStore.documents.length === 0" class="empty-documents">
        <i class="icon-inbox" aria-hidden="true"></i>
        <p>暂无文档</p>
      </div>
      
      <div v-else class="documents-list">
        <DocumentItem 
          v-for="doc in documentStore.documents" 
          :key="doc.filename" 
          :doc="doc" 
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue';
import UploadSection from './UploadSection.vue';
import DocumentItem from './DocumentItem.vue';
import { useDocumentStore } from '@/stores/documents';

const documentStore = useDocumentStore();

const onRefresh = async () => {
  try {
    await documentStore.loadDocuments();
  } catch (error: any) {
    alert(error.message);
  }
};

onMounted(() => {
  documentStore.loadDocuments();
  documentStore.startUploadJobPolling();
});

onUnmounted(() => {
  // Clean up any active pollers on settings close to avoid memory leaks
  documentStore.stopUploadJobPolling();
  documentStore.stopAllDeleteJobPolling();
});
</script>
