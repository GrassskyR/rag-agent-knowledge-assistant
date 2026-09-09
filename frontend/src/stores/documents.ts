import { defineStore } from 'pinia';
import api from '@/utils/api';
import type { DocumentItem, UploadJob, ActiveUploadJob, BatchUploadResponse, ActiveDeleteJob, DeleteStep } from '@/types/document';

export const useDocumentStore = defineStore('documents', {
  state: () => ({
    documents: [] as DocumentItem[],
    documentsLoading: false,
    selectedFiles: [] as File[],
    isUploading: false,
    uploadProgress: '',
    uploadError: '',
    uploadJobs: [] as ActiveUploadJob[],
    uploadPollTimer: null as ReturnType<typeof setTimeout> | null,
    uploadPollController: null as AbortController | null,
    deleteJobs: {} as Record<string, ActiveDeleteJob>,
    deletePollTimers: {} as Record<string, any>,
    deleteRemoveTimers: {} as Record<string, any>,
  }),

  getters: {
    uploadSummary(): string {
      const total = this.uploadJobs.length;
      if (!total) return this.uploadProgress;
      const completed = this.uploadJobs.filter((job) => job.status === 'completed').length;
      const failed = this.uploadJobs.filter((job) => job.status === 'failed').length;
      const remaining = total - completed - failed;
      return `共 ${total} 个文件，成功 ${completed} 个，失败 ${failed} 个${remaining ? `，待完成 ${remaining} 个` : ''}`;
    },
  },

  actions: {
    createDeleteSteps(): DeleteStep[] {
      return [
        { key: 'prepare', label: '准备删除', percent: 0, status: 'pending', message: '' },
        { key: 'bm25', label: '同步 BM25 统计', percent: 0, status: 'pending', message: '' },
        { key: 'milvus', label: '删除向量数据', percent: 0, status: 'pending', message: '' },
        { key: 'parent_store', label: '删除父级分块', percent: 0, status: 'pending', message: '' },
      ];
    },

    selectFiles(files: File[]) {
      if (this.isUploading) return;
      const names = new Set(this.selectedFiles.map((file) => file.name));
      for (const file of files) {
        if (!/\.(pdf|docx?|xlsx?|html?)$/i.test(file.name)) {
          throw new Error(`${file.name}：仅支持 PDF、Word、Excel 和 HTML 文档`);
        }
        if (names.has(file.name)) {
          throw new Error(`同一批次不能上传同名文件：${file.name}`);
        }
        names.add(file.name);
      }
      this.selectedFiles.push(...files);
      this.uploadError = '';
    },

    mergeDocumentsWithActiveDeletes(nextDocuments: DocumentItem[]): DocumentItem[] {
      const merged = Array.isArray(nextDocuments) ? [...nextDocuments] : [];
      Object.keys(this.deleteJobs).forEach((filename) => {
        const job = this.deleteJobs[filename];
        if (!job || job.status === 'failed') return;
        const exists = merged.some((doc) => doc.filename === filename);
        if (!exists) {
          const currentDoc = this.documents.find((doc) => doc.filename === filename);
          if (currentDoc) {
            merged.push(currentDoc);
          }
        }
      });
      return merged;
    },

    async loadDocuments() {
      this.documentsLoading = true;
      try {
        const response = await api.get('/documents');
        this.documents = this.mergeDocumentsWithActiveDeletes(response.data.documents || []);
      } catch (error: any) {
        const errMsg = error.response?.data?.detail || error.message || '加载文档列表失败';
        throw new Error(errMsg);
      } finally {
        this.documentsLoading = false;
      }
    },

    async uploadDocuments() {
      if (this.isUploading) return;
      if (!this.selectedFiles.length) {
        throw new Error('请先选择文件');
      }

      this.isUploading = true;
      this.uploadProgress = '正在上传...';
      this.uploadError = '';
      this.uploadJobs = [];

      const formData = new FormData();
      this.selectedFiles.forEach((file) => formData.append('files', file));

      try {
        const response = await api.post<BatchUploadResponse>('/documents/upload/batch/async', formData, {
          timeout: 0,
          onUploadProgress: (progressEvent) => {
            if (!progressEvent.total) return;
            const percent = Math.round((progressEvent.loaded / progressEvent.total) * 100);
            this.uploadProgress = `正在上传 ${this.selectedFiles.length} 个文件：${percent}%`;
          },
        });

        this.uploadJobs = response.data.jobs.map((job) => ({ ...job, collapsed: false }));
        this.startUploadJobPolling();
      } catch (error: any) {
        const errMsg = error.response?.data?.detail || error.message || '上传失败';
        this.uploadError = '上传失败：' + errMsg;
        this.uploadProgress = '';
        this.isUploading = false;
        throw new Error(errMsg);
      }
    },

    syncUploadJob(job: UploadJob) {
      const index = this.uploadJobs.findIndex((item) => item.job_id === job.job_id);
      if (index === -1) return;
      this.uploadJobs[index] = {
        ...job,
        collapsed: job.status === 'completed' || this.uploadJobs[index].collapsed,
      };
    },

    startUploadJobPolling() {
      this.stopUploadJobPolling();
      if (!this.isUploading || !this.uploadJobs.length) return;
      this.uploadError = '';
      const controller = new AbortController();
      this.uploadPollController = controller;

      const poll = async () => {
        const pendingJobs = this.uploadJobs.filter((job) => job.status === 'pending' || job.status === 'running');
        const results = await Promise.allSettled(pendingJobs.map((job) =>
          api.get<UploadJob>(`/documents/upload/jobs/${encodeURIComponent(job.job_id)}`, { signal: controller.signal })
        ));
        if (controller.signal.aborted) return;
        results.forEach((result) => {
          if (result.status === 'fulfilled') this.syncUploadJob(result.value.data);
        });

        const failedQuery = results.find((result) => result.status === 'rejected');
        if (failedQuery?.status === 'rejected') {
          const error = failedQuery.reason;
          this.uploadError = '进度查询失败：' + (error.response?.data?.detail || error.message);
          this.stopUploadJobPolling();
          return;
        }

        if (this.uploadJobs.every((job) => job.status === 'completed' || job.status === 'failed')) {
          this.stopUploadJobPolling();
          this.isUploading = false;
          const failedNames = new Set(this.uploadJobs.filter((job) => job.status === 'failed').map((job) => job.filename));
          this.selectedFiles = this.selectedFiles.filter((file) => failedNames.has(file.name));
          try {
            await this.loadDocuments();
          } catch (error: any) {
            this.uploadError = '文档列表刷新失败：' + error.message;
          }
          return;
        }

        this.uploadPollTimer = setTimeout(poll, 1000);
      };

      void poll();
    },

    stopUploadJobPolling() {
      if (this.uploadPollTimer) {
        clearTimeout(this.uploadPollTimer);
        this.uploadPollTimer = null;
      }
      this.uploadPollController?.abort();
      this.uploadPollController = null;
    },

    isDeletingDocument(filename: string): boolean {
      const job = this.deleteJobs[filename];
      return !!(job && job.status === 'running');
    },

    isDeleteActionLocked(filename: string): boolean {
      const job = this.deleteJobs[filename];
      return !!(job && (job.status === 'running' || job.status === 'completed'));
    },

    getDeleteButtonIcon(filename: string): string {
      const job = this.deleteJobs[filename];
      if (job?.status === 'running') return 'icon-loader-circle icon-spin';
      if (job?.status === 'completed') return 'icon-check';
      return 'icon-trash-2';
    },

    setDeleteJob(filename: string, nextJob: Partial<ActiveDeleteJob>) {
      this.deleteJobs = {
        ...this.deleteJobs,
        [filename]: {
          ...(this.deleteJobs[filename] || {
            status: 'running',
            message: '',
            collapsed: false,
            steps: this.createDeleteSteps(),
          }),
          ...nextJob,
        },
      };
    },

    syncDeleteJob(filename: string, job: any) {
      const current = this.deleteJobs[filename] || {};
      this.setDeleteJob(filename, {
        jobId: job.job_id,
        status: job.status,
        message: job.message || '',
        collapsed: job.status === 'completed' ? true : Boolean(current.collapsed),
        steps: Array.isArray(job.steps)
          ? job.steps.map((step: any) => ({
              key: step.key,
              label: step.label,
              percent: step.percent,
              status: step.status,
              message: step.message || '',
            }))
          : this.createDeleteSteps(),
      });
    },

    async deleteDocument(filename: string) {
      if (this.isDeletingDocument(filename)) {
        return;
      }
      if (!confirm(`确定要删除文档 "${filename}" 吗？这将同时删除 Milvus 中的所有相关向量。`)) {
        return;
      }

      this.clearDeleteRemovalTimer(filename);
      this.setDeleteJob(filename, {
        status: 'running',
        message: '正在提交删除任务...',
        collapsed: false,
        steps: this.createDeleteSteps().map((step) =>
          step.key === 'prepare'
            ? { ...step, percent: 1, status: 'running' as const, message: '正在提交删除任务' }
            : step
        ),
      });

      try {
        const response = await api.delete(`/documents/delete/async/${encodeURIComponent(filename)}`);
        const data = response.data;
        this.setDeleteJob(filename, {
          jobId: data.job_id,
          status: 'running',
          message: data.message || `正在删除 ${filename}`,
          collapsed: false,
        });
        this.startDeleteJobPolling(filename, data.job_id);
      } catch (error: any) {
        const errMsg = error.response?.data?.detail || error.message || '删除请求失败';
        this.setDeleteJob(filename, {
          status: 'failed',
          message: '删除文档失败：' + errMsg,
          collapsed: false,
          steps: this.deleteJobs[filename]?.steps || this.createDeleteSteps(),
        });
      }
    },

    startDeleteJobPolling(filename: string, jobId: string) {
      this.stopDeleteJobPolling(filename);

      const poll = async () => {
        try {
          const response = await api.get(`/documents/delete/jobs/${encodeURIComponent(jobId)}`);
          const job = response.data;
          this.syncDeleteJob(filename, job);

          if (job.status === 'completed') {
            this.stopDeleteJobPolling(filename);
            this.scheduleDeletedDocumentRemoval(filename);
          } else if (job.status === 'failed') {
            this.stopDeleteJobPolling(filename);
          }
        } catch (error: any) {
          const errMsg = error.response?.data?.detail || error.message || '查询失败';
          this.setDeleteJob(filename, {
            status: 'failed',
            message: '删除进度查询失败：' + errMsg,
            collapsed: false,
            steps: this.deleteJobs[filename]?.steps || this.createDeleteSteps(),
          });
          this.stopDeleteJobPolling(filename);
        }
      };

      poll();
      this.deletePollTimers = {
        ...this.deletePollTimers,
        [filename]: setInterval(poll, 1000),
      };
    },

    stopDeleteJobPolling(filename: string) {
      const timer = this.deletePollTimers[filename];
      if (!timer) return;
      clearInterval(timer);
      const { [filename]: _, ...rest } = this.deletePollTimers;
      this.deletePollTimers = rest;
    },

    stopAllDeleteJobPolling() {
      Object.keys(this.deletePollTimers).forEach((filename) => this.stopDeleteJobPolling(filename));
    },

    clearDeleteRemovalTimer(filename: string) {
      const timer = this.deleteRemoveTimers[filename];
      if (!timer) return;
      clearTimeout(timer);
      const { [filename]: _, ...rest } = this.deleteRemoveTimers;
      this.deleteRemoveTimers = rest;
    },

    scheduleDeletedDocumentRemoval(filename: string) {
      this.clearDeleteRemovalTimer(filename);
      const timer = setTimeout(async () => {
        this.documents = this.documents.filter((doc) => doc.filename !== filename);
        const { [filename]: _job, ...jobs } = this.deleteJobs;
        const { [filename]: _timer, ...timers } = this.deleteRemoveTimers;
        this.deleteJobs = jobs;
        this.deleteRemoveTimers = timers;
        await this.loadDocuments();
      }, 3000);
      this.deleteRemoveTimers = {
        ...this.deleteRemoveTimers,
        [filename]: timer,
      };
    },

    toggleDeleteJobCollapsed(filename: string) {
      const job = this.deleteJobs[filename];
      if (!job) return;
      this.setDeleteJob(filename, { collapsed: !job.collapsed });
    },
  },
});
export type { DocumentItem };
