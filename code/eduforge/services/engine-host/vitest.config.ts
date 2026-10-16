import { defineConfig } from "vitest/config";

// 必须显式给 root：vitest 默认会沿目录向上找 vite 配置，
// 本机在 D:\ 根盘存在一个游离的 vite.config.ts（引用未安装的 @tailwindcss/vite），
// 不锁 root 就会加载它并启动失败。
export default defineConfig({
  root: import.meta.dirname,
  test: {
    include: ["tests/**/*.test.ts"],
    environment: "node",
    // 三个 e2e 各自起真实 Chromium；并行时 CPU 争抢会让"等渲染稳定"在
    // 平台期误判完成，控制组哈希就会偶发不一致。实测串行跑完全确定，故 e2e 串行。
    fileParallelism: false,
  },
});
