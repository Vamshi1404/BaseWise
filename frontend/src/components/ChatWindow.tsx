import React, { useState, useEffect, useRef } from 'react';
import { Send, Sparkles, Loader2, BarChart2 } from 'lucide-react';
import { convApi, analysisApi } from '../api/client';
import type { Message, QueryResultPayload } from '../types';
import { MessageItem } from './MessageItem';

interface ChatWindowProps {
  conversationId: string;
  dbId: string;
  mode: 'query' | 'analysis';
}

export const ChatWindow: React.FC<ChatWindowProps> = ({ conversationId, dbId, mode }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [resultPayloads, setResultPayloads] = useState<Record<string, QueryResultPayload>>({});
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [statusSteps, setStatusSteps] = useState<string[]>([]);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [hasTokens, setHasTokens] = useState(false);
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const streamingIdRef = useRef<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!conversationId) return;
    convApi.getMessages(conversationId).then((res) => {
      setMessages(res.data);
    }).catch(console.error);

    if (mode === 'analysis') {
      analysisApi.suggest(dbId).then((res) => {
        setSuggestions(res.data.suggestions || []);
      }).catch(console.error);
    }
  }, [conversationId, dbId, mode]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, statusMsg]);

  const handleSend = (textToSend?: string) => {
    const content = textToSend || prompt;
    if (!content.trim() || loading) return;

    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      conversation_id: conversationId,
      role: 'user',
      content: content.trim(),
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, tempUserMsg]);
    if (!textToSend) setPrompt('');
    setLoading(true);
    setStatusMsg('Connecting...');
    setStatusSteps([]);
    setErrorMsg(null);
    setHasTokens(false);
    streamingIdRef.current = null;
    setStreamingId(null);

    const trackStatus = (s: string) => {
      setStatusSteps((prev) => (prev[prev.length - 1] === s ? prev : [...prev, s]));
      setStatusMsg(s);
    };

    const handleToken = (delta: string) => {
      setHasTokens(true);
      const id = streamingIdRef.current;
      if (id) {
        setMessages((prev) =>
          prev.map((m) => (m.id === id ? { ...m, content: m.content + delta } : m))
        );
      } else {
        const newMsg: Message = {
          id: `stream-${Date.now()}`,
          conversation_id: conversationId,
          role: 'assistant',
          content: delta,
          created_at: new Date().toISOString(),
        };
        streamingIdRef.current = newMsg.id;
        setStreamingId(newMsg.id);
        setMessages((prev) => [...prev, newMsg]);
      }
    };

    const finishStream = () => {
      setLoading(false);
      setStatusMsg(null);
      setHasTokens(false);
      streamingIdRef.current = null;
      setStreamingId(null);
    };

    if (mode === 'analysis') {
      analysisApi.executeStream(
        conversationId,
        content.trim(),
        trackStatus,
        (resultPayload) => {
          const assistantMsg = resultPayload.message ?? {
            id: `asst-${Date.now()}`,
            conversation_id: conversationId,
            role: 'assistant' as const,
            content: 'Analysis executed successfully.',
            chart_data: resultPayload.chart_data || null,
            created_at: new Date().toISOString(),
          };
          setMessages((prev) => [...prev, assistantMsg]);
          finishStream();
        },
        (error) => {
          console.error(error);
          finishStream();
          setErrorMsg(`Error: ${error}`);
        }
      );
    } else {
      convApi.sendMessageStream(
        conversationId,
        content.trim(),
        trackStatus,
        handleToken,
        (resultPayload) => {
          const streamId = streamingIdRef.current;
          setMessages((prev) => {
            const kept = streamId ? prev.filter((m) => m.id !== streamId) : prev;
            return [...kept, resultPayload.message];
          });
          setResultPayloads((prev) => ({
            ...prev,
            [resultPayload.message.id]: resultPayload,
          }));
          finishStream();
        },
        (error) => {
          console.error(error);
          finishStream();
          setErrorMsg(`Error: ${error}`);
        }
      );
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-[#0B0F17] overflow-hidden">
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-8 max-w-xl mx-auto space-y-6">
            <div className="w-16 h-16 rounded-3xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center text-white shadow-2xl shadow-cyan-500/30">
              {mode === 'analysis' ? <BarChart2 className="w-8 h-8" /> : <Sparkles className="w-8 h-8" />}
            </div>
            <div>
              <h3 className="text-xl font-bold text-slate-100">
                {mode === 'analysis' ? 'Proactive Business Analysis' : 'Ask Anything in Plain English'}
              </h3>
              <p className="text-xs text-slate-400 mt-2 leading-relaxed">
                {mode === 'analysis'
                  ? 'Basewise automatically inspects your schema and runs sandboxed Python code to compute insights & render interactive visualizations.'
                  : 'Basewise converts your question into validated SQL, self-rechecks for errors, and runs the query cleanly.'}
              </p>
            </div>

            {mode === 'analysis' && suggestions.length > 0 && (
              <div className="w-full space-y-2 pt-2">
                <div className="text-[11px] font-semibold text-purple-400 uppercase tracking-wider text-left">
                  Suggested Business Insights:
                </div>
                <div className="flex flex-col space-y-2">
                  {suggestions.map((s, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSend(s)}
                      className="text-left px-4 py-2.5 rounded-xl glass-card text-xs text-slate-200 hover:text-cyan-300 hover:border-cyan-500/40 transition-all flex items-center justify-between group"
                    >
                      <span>{s}</span>
                      <Sparkles className="w-3.5 h-3.5 text-purple-400 group-hover:scale-110 transition-transform" />
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          messages.map((m, i) => (
            <MessageItem
              key={m.id}
              message={m}
              resultPayload={resultPayloads[m.id]}
              streaming={hasTokens && loading && m.id === streamingId}
              typewriter={mode === 'analysis' && loading && i === messages.length - 1 && m.role === 'assistant'}
            />
          ))
        )}

        {loading && !hasTokens && (
          <div className="flex items-start space-x-3 mb-8">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center text-white shrink-0 shadow-md shadow-cyan-500/20">
              <Sparkles className="w-5 h-5" />
            </div>
            <div className="flex-1 max-w-3xl">
              <div className="rounded-2xl glass-panel p-4 border border-slate-800 inline-block min-w-[260px]">
                <div className="flex items-center space-x-2 mb-3">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="text-[11px] uppercase tracking-wider font-mono text-cyan-400 ml-1 animate-pulse-glow">
                    thinking
                  </span>
                </div>
                {statusSteps.length > 0 && (
                  <div className="space-y-1.5">
                    {statusSteps.map((step, i) => {
                      const isCurrent = i === statusSteps.length - 1;
                      return (
                        <div key={i} className="flex items-center space-x-2 text-xs">
                          {isCurrent ? (
                            <Loader2 className="w-3 h-3 animate-spin text-cyan-400 shrink-0" />
                          ) : (
                            <span className="w-3 h-3 rounded-full bg-emerald-500/80 flex items-center justify-center text-[8px] text-white shrink-0">✓</span>
                          )}
                          <span className={isCurrent ? 'text-cyan-200' : 'text-slate-400'}>{step}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {errorMsg && !loading && (
        <div className="px-6 pb-2">
          <div className="max-w-md mx-auto rounded-2xl border border-red-500/40 bg-red-950/40 p-4 text-xs text-red-200 flex items-center space-x-2">
            <span>⚠</span>
            <span>{errorMsg}</span>
          </div>
        </div>
      )}

      <div className="p-4 border-t border-slate-800/80 bg-[#0B0F17]/90 backdrop-blur-md">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="max-w-4xl mx-auto relative flex items-center"
        >
          <input
            type="text"
            placeholder={
              mode === 'analysis'
                ? 'e.g. Analyze revenue growth by month and product category...'
                : 'e.g. Show me total sales by region for last quarter...'
            }
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={loading}
            className="w-full pl-5 pr-14 py-4 rounded-2xl bg-slate-900/90 border border-slate-800 text-slate-100 placeholder-slate-500 text-sm focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 shadow-inner"
          />
          <button
            type="submit"
            disabled={!prompt.trim() || loading}
            className="absolute right-2 p-2.5 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 text-white hover:scale-105 active:scale-95 transition-all disabled:opacity-40 disabled:hover:scale-100"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </button>
        </form>
      </div>
    </div>
  );
};
