# EduForge TypeScript Engine Host 仿真服务 Dockerfile
FROM node:24-alpine

WORKDIR /app

ENV NODE_ENV=production

# 拷贝 package.json 与依赖
COPY services/engine-host/package.json ./services/engine-host/
RUN cd services/engine-host && npm install --omit=dev

# 拷贝代码与依赖资源
COPY services/engine-host ./services/engine-host
COPY catalog ./catalog

EXPOSE 4000

WORKDIR /app/services/engine-host
CMD ["node", "dist/main.js"]
