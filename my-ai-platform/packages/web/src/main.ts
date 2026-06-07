/**
 * Vue 3 应用入口
 * 对应 MD §5.1 — Vue 3 + Vite + Tailwind
 */
import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";

const app = createApp(App);
app.use(createPinia());
app.mount("#app");
