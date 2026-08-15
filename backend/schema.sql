-- ====================================================================
-- Basewise Platform — Supabase Database Migration DDL Script
-- Run this entire script in your Supabase SQL Editor to set up all tables.
-- ====================================================================

-- Enable pgcrypto for UUID generation if not already enabled
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Drop tables if re-initializing (cascade handles dependencies)
DROP TABLE IF EXISTS query_runs CASCADE;
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS conversations CASCADE;
DROP TABLE IF EXISTS schema_cache CASCADE;
DROP TABLE IF EXISTS linked_databases CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Drop custom enum types if re-initializing
DROP TYPE IF EXISTS conversation_mode CASCADE;
DROP TYPE IF EXISTS message_role CASCADE;
DROP TYPE IF EXISTS operation_type CASCADE;
DROP TYPE IF EXISTS run_status CASCADE;

-- Create Enum Types
CREATE TYPE conversation_mode AS ENUM ('query', 'analysis');
CREATE TYPE message_role AS ENUM ('user', 'assistant');
CREATE TYPE operation_type AS ENUM ('read', 'write', 'ddl');
CREATE TYPE run_status AS ENUM ('success', 'error');

-- 1. Users Table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_users_email ON users(email);

-- 2. Linked Databases Table (Fernet symmetric encryption)
CREATE TABLE linked_databases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    db_type VARCHAR(50) DEFAULT 'postgres' NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    encrypted_credentials TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    last_schema_scan_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_linked_databases_user_id ON linked_databases(user_id);

-- 3. Schema Cache Table
CREATE TABLE schema_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    linked_database_id UUID NOT NULL REFERENCES linked_databases(id) ON DELETE CASCADE UNIQUE,
    schema_json JSONB NOT NULL,
    scanned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- 4. Conversations Table
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    linked_database_id UUID NOT NULL REFERENCES linked_databases(id) ON DELETE CASCADE,
    mode conversation_mode DEFAULT 'query' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_conversations_linked_db ON conversations(linked_database_id);

-- 5. Messages Table
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role message_role NOT NULL,
    content TEXT NOT NULL,
    sql_generated TEXT,
    confidence_score DOUBLE PRECISION,
    reasoning TEXT,
    chart_data JSONB,
    -- #6: structured explanation of how confidence_score was derived
    confidence_trace JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);

-- 6. Query Runs Audit Log Table
CREATE TABLE query_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
    sql_text TEXT NOT NULL,
    operation_type operation_type DEFAULT 'read' NOT NULL,
    row_count INT DEFAULT 0,
    rows_affected INT DEFAULT 0,
    execution_ms INT NOT NULL,
    sandbox_session_id VARCHAR(255),
    status run_status NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_query_runs_message_id ON query_runs(message_id);
