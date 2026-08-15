export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface LinkedDatabase {
  id: string;
  display_name: string;
  db_type: string;
  created_at: string;
  last_schema_scan_at?: string | null;
}

export interface ColumnSchema {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
}

export interface ForeignKeySchema {
  column: string;
  references_table: string;
  references_column: string;
}

export interface TableSchema {
  name: string;
  columns: ColumnSchema[];
  primary_keys: string[];
  foreign_keys: ForeignKeySchema[];
  row_count?: number | null;
}

export interface SchemaData {
  tables: TableSchema[];
  dialect: string;
  scanned_at: string;
}

export interface Conversation {
  id: string;
  mode: 'query' | 'analysis';
  linked_database_id: string;
  created_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  sql_generated?: string | null;
  confidence_score?: number | null;
  confidence_label?: 'high' | 'medium' | 'low' | null;
  reasoning?: string | null;
  chart_data?: ChartSpec | null;
  created_at: string;
}

export interface QueryResultPayload {
  message: Message;
  results?: Record<string, any>[] | null;
  chart_data?: ChartSpec | null;
  row_count?: number;
  rows_affected?: number;
  operation_type?: 'read' | 'write' | 'ddl';
  execution_ms?: number;
  confidence_label?: 'high' | 'medium' | 'low';
  reasoning?: string | null;
  summary?: string | null;
  status: 'success' | 'error';
  error?: string | null;
}

export interface ChartSpec {
  type: 'bar' | 'line' | 'pie' | 'area' | 'scatter' | 'funnel' | 'treemap' | 'table';
  title?: string;
  data: Record<string, any>[];
  x_key?: string;
  y_keys?: string[];
  z_key?: string;
  value_key?: string;
  summary?: string;
}

export interface AnalysisResultPayload {
  message: Message;
  chart_data?: ChartSpec | null;
  python_code?: string;
  execution_ms?: number;
  status: 'success' | 'error';
  error?: string | null;
}
