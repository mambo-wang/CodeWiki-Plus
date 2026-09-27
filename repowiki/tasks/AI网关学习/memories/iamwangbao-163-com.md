### 2026-09-27 15:05 #f6fe

Higress Windows 安装调研结论：Higress 无原生 Windows 安装方式，本地部署唯一路径是 Docker all-in-one 镜像（higress-registry.cn-hangzhou.cr.aliyuncs.com/higress/all-in-one，端口 8001 控制台/8080 HTTP/8443 HTTPS）。本机环境：Windows 10 企业版 1909 build 18363，无 Docker、无 WSL，build<19041 不支持 WSL2，但 CPU 虚拟化已启用、企业版支持 Hyper-V——推荐方案是 Docker Desktop Hyper-V 后端（需重启启用 Hyper-V），已向用户确认是否执行安装。另：本机 Node v20.19.0 低于 OmniRoute 要求的 ≥22.22.2，已通过 install_binary 装好 Node 22.22.2（C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2），omniroute npm 安装尚未完成（用户取消）。

### 2026-09-27 15:51 #u6h0

用户最终决定：OmniRoute 也不安装。任务「AI网关学习」本轮调研结束，结论：Higress 与 OmniRoute 均不在本机部署——Higress 无原生 Windows 支持且用户不装 Docker；OmniRoute 安装被叫停（Node 22.22.2 已装好备用）。如后续需要体验 AI 网关，可用官方在线 demo（demo.higress.io / mcp.higress.ai）或远程 Linux 服务器。
