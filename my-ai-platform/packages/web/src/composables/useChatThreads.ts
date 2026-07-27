import { ref } from "vue";
import { getOrCreateSessionId } from "../chat/model";

export interface ChatThread {
  session_id: string;
  title: string;
  preview: string;
  message_count: number;
  updated_at: string;
  agent_ids: string[];
}

export function useChatThreads() {
  const activeSessionId = ref(getOrCreateSessionId());
  const threads = ref<ChatThread[]>([]);
  const loadingThreads = ref(false);

  async function refreshThreads() {
    loadingThreads.value = true;
    try {
      const response = await fetch("/chat/threads");
      if (!response.ok) return;
      const data = await response.json();
      threads.value = data.threads || [];
    } finally {
      loadingThreads.value = false;
    }
  }

  function selectThread(sessionId: string) {
    activeSessionId.value = sessionId;
    sessionStorage.setItem("chat_session_id", sessionId);
  }

  function createThread() {
    const sessionId = crypto.randomUUID();
    selectThread(sessionId);
    return sessionId;
  }

  return {
    activeSessionId,
    threads,
    loadingThreads,
    refreshThreads,
    selectThread,
    createThread,
  };
}
