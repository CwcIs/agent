export async function readSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onEvent: (eventType: string, data: string) => void,
  signal: AbortSignal,
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (block: string) => {
    let eventType = "";
    let data = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) eventType = line.slice(7).trim();
      else if (line.startsWith("data: ")) data = line.slice(6);
    }
    if (eventType) onEvent(eventType, data);
  };

  try {
    while (!signal.aborted) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n");
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        if (part.trim()) dispatch(part);
      }
    }
    if (buffer.trim()) dispatch(buffer);
  } catch (error: unknown) {
    if (!signal.aborted) console.error("SSE stream read error:", error);
  } finally {
    reader.releaseLock();
  }
}

