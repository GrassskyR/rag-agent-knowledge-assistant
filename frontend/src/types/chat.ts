export interface RetrievedChunk {
  filename: string;
  page_number?: number;
  rrf_rank?: number;
  rerank_score?: number | null;
  text?: string;
  url?: string;
  title?: string;
  source_type?: string;
  engine?: string;
  fetched?: boolean;
}

export interface RagTrace {
  tool_used?: boolean;
  tool_name?: string;
  retrieval_stage?: string;
  grade_score?: number;
  grade_route?: string;
  rewrite_needed?: boolean;
  rewrite_strategy?: string;
  rewrite_query?: string;
  retrieval_pipeline?: string;
  retrieval_mode?: string;
  candidate_k?: number;
  candidate_k_config_error?: string;
  candidate_k_source?: string;
  retrieval_candidate_multiplier?: number;
  recall_count?: number | null;
  post_merge_candidate_count?: number | null;
  candidate_count?: number | null;
  retrieval_top_k?: number;
  retrieved_chunks?: RetrievedChunk[];
  leaf_retrieve_level?: number;
  auto_merge_enabled?: boolean | null;
  auto_merge_applied?: boolean | null;
  auto_merge_threshold?: number;
  auto_merge_replaced_chunks?: number;
  auto_merge_steps?: number;
  rerank_enabled?: boolean | null;
  rerank_applied?: boolean | null;
  rerank_model?: string;
  rerank_error?: string;
  expansion_type?: string;
  step_back_question?: string;
  expanded_query?: string;
  hypothetical_doc?: string;
  complexity?: 'simple' | 'complex' | string;
  complexity_reason?: string;
  sub_questions?: string[];
  sub_agent_count?: number;
  synthesis_merged_count?: number;
  sub_traces?: any[];
  initial_retrieved_chunks?: RetrievedChunk[];
  expanded_retrieved_chunks?: RetrievedChunk[];
  web_search_used?: boolean;
  tool_query?: string;
  web_query?: string;
  web_result_count?: number;
  web_results?: RetrievedChunk[];
  web_sources?: RetrievedChunk[];
  web_engines?: string[];
  web_partial_failures?: any[];
  web_fetch_decision?: string;
  web_fetch_urls?: string[];
  web_fetch_count?: number;
  web_fetched_pages?: any[];
  rag_fallback_reason?: string;
}

export interface RagStep {
  key?: string;
  group?: string | null;
  label: string;
  icon?: string;
  detail?: string;
  status?: string;
  percent?: number;
  message?: string;
}

export interface GroupedRagStep {
  group: string | null;
  label: string | null;
  steps: RagStep[];
  collapsed: boolean;
}

export interface Message {
  text: string;
  isUser: boolean;
  isThinking?: boolean;
  ragTrace?: RagTrace | null;
  ragSteps?: RagStep[];
  _groupedSteps?: GroupedRagStep[];
  images?: string[];
}

export interface ChatSession {
  session_id: string;
  title?: string;
  message_count: number;
  updated_at: string;
}
