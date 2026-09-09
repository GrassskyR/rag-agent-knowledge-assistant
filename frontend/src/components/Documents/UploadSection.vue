<template>
  <div class="upload-section">
    <h3><i class="icon-upload" aria-hidden="true"></i> 上传文档</h3>
    <div class="upload-area">
      <ElUpload
        class="document-upload"
        action="#"
        drag
        multiple
        :auto-upload="false"
        :show-file-list="false"
        accept=".pdf,.doc,.docx,.xls,.xlsx,.html,.htm"
        :disabled="documentStore.isUploading"
        :on-change="onFileChange"
      >
        <i class="icon-cloud-upload document-upload-icon" aria-hidden="true"></i>
        <div class="el-upload__text">将文件拖到此处，或 <em>点击选择文件</em></div>
        <template #tip>
          <div class="el-upload__tip">支持 PDF、Word、Excel 和 HTML 文档，可同时选择多个文件</div>
        </template>
      </ElUpload>

      <div class="upload-actions">
        <button v-if="documentStore.selectedFiles.length" @click="onUpload" class="btn-primary" :disabled="documentStore.isUploading">
          <i class="icon-upload" aria-hidden="true"></i>
          {{ documentStore.isUploading ? '处理中...' : `上传 ${documentStore.selectedFiles.length} 个文件` }}
        </button>
      </div>

      <ul v-if="documentStore.selectedFiles.length && !documentStore.isUploading" class="selected-file-list">
        <li v-for="(file, index) in documentStore.selectedFiles" :key="file.name" class="selected-file">
          <i class="icon-file" aria-hidden="true"></i>
          <span class="selected-file-name">{{ file.name }}</span>
          <button type="button" class="upload-remove" :title="`移除 ${file.name}`" :aria-label="`移除 ${file.name}`" @click="documentStore.selectedFiles.splice(index, 1)">
            <i class="icon-x" aria-hidden="true"></i>
          </button>
        </li>
      </ul>

      <p v-if="documentStore.uploadSummary" class="upload-summary" role="status">{{ documentStore.uploadSummary }}</p>
      <div v-if="documentStore.uploadError" class="upload-error" role="alert">
        <span>{{ documentStore.uploadError }}</span>
        <button v-if="documentStore.isUploading && documentStore.uploadJobs.length" class="btn-secondary" @click="documentStore.startUploadJobPolling()">
          <i class="icon-refresh-cw" aria-hidden="true"></i> 重试查询
        </button>
      </div>

      <div v-for="job in documentStore.uploadJobs" :key="job.job_id" class="upload-progress" :class="{ collapsed: job.collapsed }">
        <button type="button" class="upload-progress-header" :aria-expanded="!job.collapsed" :aria-label="`${job.collapsed ? '展开' : '收起'} ${job.filename} 的上传进度`" @click="job.collapsed = !job.collapsed">
          <span class="upload-job-title">
            <span class="upload-message">{{ job.filename }}</span>
            <span class="upload-job-status" :class="{ 'upload-error': job.status === 'failed' }">{{ statusLabels[job.status] }}</span>
          </span>
          <i :class="job.collapsed ? 'icon-chevron-down' : 'icon-chevron-up'" aria-hidden="true"></i>
        </button>
        <p class="upload-job-message" :class="{ 'upload-error': job.status === 'failed' }">{{ job.message }}</p>

        <div v-show="!job.collapsed" class="upload-step-list">
          <div
            v-for="step in job.steps"
            :key="step.key"
            class="upload-step"
            :class="`upload-step-${step.status}`"
          >
            <div class="upload-step-header">
              <span class="upload-step-label">{{ step.label }}</span>
              <span class="upload-step-percent">{{ step.percent }}%</span>
            </div>
            <div class="upload-step-bar" role="progressbar" :aria-label="`${job.filename} ${step.label}`" :aria-valuenow="step.percent" :aria-valuemin="0" :aria-valuemax="100">
              <div class="upload-step-fill" :style="{ width: step.percent + '%' }"></div>
            </div>
            <div v-if="step.message" class="upload-step-message">{{ step.message }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElUpload } from 'element-plus';
import type { UploadFile } from 'element-plus';
import { useDocumentStore } from '@/stores/documents';

const documentStore = useDocumentStore();
const statusLabels = { pending: '等待处理', running: '处理中', completed: '已完成', failed: '失败' };

const onFileChange = (uploadFile: UploadFile) => {
  const file = uploadFile.raw;
  if (!file) return;

  try {
    documentStore.selectFiles([file]);
  } catch (error: unknown) {
    documentStore.uploadError = error instanceof Error ? error.message : '文件选择失败';
  }
};

const onUpload = async () => {
  try {
    await documentStore.uploadDocuments();
  } catch (error: any) {
    alert('上传文档失败: ' + error.message);
  }
};

</script>
