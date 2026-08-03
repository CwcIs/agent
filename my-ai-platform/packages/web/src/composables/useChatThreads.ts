import { ref } from "vue";
import { getOrCreateSessionId } from "../chat/model";

export interface ChatThread {
  session_id: string;
  title: string;
  preview: string;
  message_count: number;
  updated_at: string;
  agent_ids: string[];
  pinned: boolean;
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

  async function updateThread(
    sessionId: string,
    patch: { title?: string; pinned?: boolean; archived?: boolean },
  ) {
    const response = await fetch(`/chat/threads/${encodeURIComponent(sessionId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (!response.ok) {
      throw new Error(`Failed to update thread: ${response.status}`);
    }
    await refreshThreads();
    if (patch.archived && activeSessionId.value === sessionId) {
      createThread();
    }
  }

  return {
    activeSessionId,
    threads,
    loadingThreads,
    refreshThreads,
    selectThread,
    createThread,
    updateThread,
  };
}
