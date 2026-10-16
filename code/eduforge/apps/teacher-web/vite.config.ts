import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发时也要保持"浏览器只面对一个源"：§5.3 的桥接对入站消息做同源校验，
// 所以 dev server 把预览与 API 路径代理到网关，而不是让前端直连两个端口。
const gateway = process.env.EDUFORGE_GATEWAY_URL ?? "http://127.0.0.1:4174";
const proxied = ["/api", "/scene", "/param", "/p", "/host", "/simulator", "/locales"];

export default defineConfig({
  root: import.meta.dirname,
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      proxied.map(p => [p, { target: gateway, changeOrigin: false }])
    ),
  },
  build: { outDir: "dist", emptyOutDir: true },
});
