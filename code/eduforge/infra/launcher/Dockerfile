# EduForge 本地轻量离线启动器编译 Dockerfile
FROM golang:1.22-alpine AS builder

WORKDIR /src
COPY tools/offline-server .

RUN CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -ldflags="-s -w" -o /out/Start-Experiment.exe .

FROM scratch
COPY --from=builder /out/Start-Experiment.exe /Start-Experiment.exe
