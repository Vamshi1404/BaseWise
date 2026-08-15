import React, { useState, useEffect } from 'react';
import { dbApi, convApi } from '../api/client';
import type { LinkedDatabase, SchemaData, Conversation } from '../types';
import { SchemaViewer } from '../components/SchemaViewer';
import { ChatWindow } from '../components/ChatWindow';

interface DatabaseWorkspaceProps {
  database: LinkedDatabase;
  mode: 'query' | 'analysis';
}

export const DatabaseWorkspace: React.FC<DatabaseWorkspaceProps> = ({ database, mode }) => {
  const [schema, setSchema] = useState<SchemaData | null>(null);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [conversation, setConversation] = useState<Conversation | null>(null);

  const loadSchema = () => {
    setSchemaLoading(true);
    dbApi.getSchema(database.id).then((res) => {
      setSchema(res.data);
    }).catch(console.error).finally(() => setSchemaLoading(false));
  };

  const forceRefreshSchema = () => {
    setSchemaLoading(true);
    dbApi.refreshSchema(database.id).then((res) => {
      setSchema(res.data);
    }).catch(console.error).finally(() => setSchemaLoading(false));
  };

  useEffect(() => {
    loadSchema();
    convApi.list(database.id, mode).then((res) => {
      if (res.data.length > 0) {
        setConversation(res.data[0]);
      } else {
        convApi.create(database.id, mode).then((createdRes) => {
          setConversation(createdRes.data);
        });
      }
    }).catch(console.error);
  }, [database.id, mode]);

  return (
    <div className="h-[calc(100vh-4rem)] flex overflow-hidden">
      <SchemaViewer
        schema={schema}
        loading={schemaLoading}
        onRefresh={forceRefreshSchema}
      />

      {conversation ? (
        <ChatWindow
          conversationId={conversation.id}
          dbId={database.id}
          mode={mode}
        />
      ) : (
        <div className="flex-1 flex items-center justify-center text-slate-500 text-xs">
          Loading workspace session...
        </div>
      )}
    </div>
  );
};
