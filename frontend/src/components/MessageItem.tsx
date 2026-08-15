import React, { useState } from 'react';
import { User as UserIcon, Bot, Code, Copy, Check, ChevronDown, ChevronUp } from 'lucide-react';
import type { Message, QueryResultPayload } from '../types';
import { ConfidenceBadge } from './ConfidenceBadge';
import { QueryResultTable } from './QueryResultTable';
import { ChartRenderer } from './ChartRenderer';
import { useTypewriter } from '../hooks/useTypewriter';

interface MessageItemProps {
  message: Message;
  resultPayload?: QueryResultPayload | null;
  streaming?: boolean; // real token stream in progress — show text as it grows + caret
  typewriter?: boolean; // fake typewriter effect (used when no real token stream)
}

export const MessageItem: React.FC<MessageItemProps> = ({ message, resultPayload, streaming, typewriter }) => {
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState(false);
  const [showSql, setShowSql] = useState(true);
  const [showReasoning, setShowReasoning] = useState(false);
  const typedContent = useTypewriter(typewriter ? message.content : '', 12);
  const displayContent = streaming ? message.content : (typewriter ? typedContent : message.content);
  const showCaret = streaming || (typewriter && typedContent.length < message.content.length);

  const copySql = () => {
    if (message.sql_generated) {
      navigator.clipboard.writeText(message.sql_generated);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (isUser) {
    return (
      <div className="flex items-start space-x-3 justify-end mb-6">
        <div className="max-w-2xl px-5 py-3.5 rounded-2xl rounded-tr-none bg-gradient-to-r from-cyan-600 to-blue-600 text-white text-sm font-medium shadow-lg shadow-cyan-500/10">
          {message.content}
        </div>
        <div className="w-9 h-9 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-cyan-400 shrink-0">
          <UserIcon className="w-5 h-5" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start space-x-3 mb-8">
      <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center text-white shrink-0 shadow-md shadow-cyan-500/20">
        <Bot className="w-5 h-5" />
      </div>

      <div className="flex-1 max-w-3xl space-y-4">
        {message.confidence_score !== undefined && message.confidence_score !== null && (
          <div>
            <ConfidenceBadge
              score={message.confidence_score}
              label={message.confidence_label}
            />
          </div>
        )}

        {message.reasoning && (
          <div className="rounded-2xl bg-slate-900/70 border border-slate-800/80 overflow-hidden">
            <button
              onClick={() => setShowReasoning(!showReasoning)}
              className="w-full px-4 py-2.5 flex items-center justify-between text-xs font-semibold text-slate-300 hover:text-amber-300 transition-colors"
            >
              <span className="flex items-center space-x-2">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                <span>Why this query</span>
              </span>
              {showReasoning ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
            {showReasoning && (
              <p className="px-4 pb-4 text-xs text-slate-300 leading-relaxed">
                {message.reasoning}
              </p>
            )}
          </div>
        )}

        {message.sql_generated && (
          <div className="rounded-2xl bg-slate-950 border border-slate-800 overflow-hidden">
            <div className="px-4 py-2.5 bg-slate-900/90 border-b border-slate-800/80 flex items-center justify-between">
              <button
                onClick={() => setShowSql(!showSql)}
                className="flex items-center space-x-2 text-xs font-semibold text-slate-300 hover:text-cyan-400 transition-colors"
              >
                <Code className="w-4 h-4 text-cyan-400" />
                <span>Validated SQL Query</span>
                {showSql ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>

              <button
                onClick={copySql}
                className="flex items-center space-x-1 text-[11px] text-slate-400 hover:text-slate-200 transition-colors"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copied ? 'Copied' : 'Copy'}</span>
              </button>
            </div>

            {showSql && (
              <pre className="p-4 text-xs font-mono text-cyan-300 overflow-x-auto bg-slate-950/90 leading-relaxed">
                <code>{message.sql_generated}</code>
              </pre>
            )}
          </div>
        )}

        <div className="text-sm text-slate-200 leading-relaxed glass-panel p-4 rounded-2xl border border-slate-800">
          {displayContent}
          {showCaret && (
            <span className="typing-caret" />
          )}
        </div>

        {(message.chart_data || resultPayload?.chart_data) && (
          <ChartRenderer spec={message.chart_data || resultPayload?.chart_data} />
        )}

        {resultPayload && (
          <QueryResultTable
            rows={resultPayload.results}
            rowCount={resultPayload.row_count}
            rowsAffected={resultPayload.rows_affected}
            operationType={resultPayload.operation_type}
            executionMs={resultPayload.execution_ms}
          />
        )}
      </div>
    </div>
  );
};
