export type WorkspaceSurface = "studio" | "trace" | "graph" | "profile" | "admin";
export type KnowledgeSection = "inbox" | "notes" | "archive";

export const knowledgeNavigation: Array<{
  id: KnowledgeSection;
  label: string;
  description: string;
}> = [
  { id: "inbox", label: "Inbox", description: "今天捕捉的新想法" },
  { id: "notes", label: "Notes", description: "有效与演进中的知识" },
  { id: "archive", label: "Archive", description: "已归档内容" },
];
