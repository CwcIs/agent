import { ref } from "vue";

export type DrawerPanel = 'related_notes' | 'review_findings' | 'brain_expansions' | 'tool_details';

export function useInsightDrawer() {
  const drawerOpen = ref(false);
  const activePanel = ref<DrawerPanel | null>(null);
  const panelPayload = ref<unknown>(null);
  const drawerTitle = ref('');

  function open(panel: DrawerPanel, payload: unknown = null, title: string = '') {
    activePanel.value = panel;
    panelPayload.value = payload;
    drawerTitle.value = title || panelLabel(panel);
    drawerOpen.value = true;
  }

  function close() {
    drawerOpen.value = false;
    activePanel.value = null;
    panelPayload.value = null;
  }

  function panelLabel(panel: DrawerPanel): string {
    switch (panel) {
      case 'related_notes':    return 'Related Notes';
      case 'review_findings':  return 'Review Findings';
      case 'brain_expansions': return 'Brain Expansions';
      case 'tool_details':     return 'Tool Details';
    }
  }

  return { drawerOpen, activePanel, panelPayload, drawerTitle, open, close };
}
