# EduForge 受限代码定制沙箱环境 Dockerfile
FROM node:24-alpine

WORKDIR /workspace

RUN apk add --no-cache git python3 make g++

# 预创建标准工作区目录结构
RUN mkdir -p /workspace/src /workspace/dist /workspace/tests

# 默认禁止联网（由 OpenSandbox 运行时参数控制 network_disabled=True）
USER node

CMD ["sh"]
