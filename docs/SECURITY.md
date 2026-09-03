# 安全设计

## 信任边界

API 参数、导入文件、用户代码和动态语言命令均视为不可信。管理员上传的 SPJ 仍会进行
静态检查，并在 Docker 后端下隔离运行。`local` 后端仅用于开发和基础验收；它不能阻止
代码读取宿主文件或访问网络。

## 已实现控制

### 身份与数据

- 密码使用 PBKDF2-HMAC-SHA256、随机 16 字节 salt 和常量时间比较。
- 导入哈希会校验算法、迭代次数上限、Base64 和摘要长度，防止明文和计算量攻击。
- Session ID 使用密码学安全随机数，服务端保存并设置过期时间；登出立即删除。
- Cookie 使用 `HttpOnly`、`SameSite=Lax`；HTTPS 部署设置 `OJ_SECURE_COOKIES=true`。
- 所有角色检查在业务操作前完成；banned 用户返回 403。
- JSON 状态由进程内锁串行修改，先写临时文件再原子替换。
- 导入先完整验证，失败不会写入半份数据；导入成功会清空已有 Session。

### 命令与进程

- 使用 `create_subprocess_exec` 和参数数组，不启用 shell。
- 动态命令采用可执行文件白名单，拒绝 shell 控制符、未知占位符和格式转换。
- 本地后端同时使用操作系统地址空间限制和 `psutil` 进程树监控。
- 超时终止整个进程组；应用关闭、重置和重新评测都会取消并等待旧任务。
- stdout/stderr 各最多保留 4 MiB；超量立即终止，防止父进程内存耗尽。
- 用户源码、可执行文件和测例仅位于每次任务独立的临时目录。

### Docker 后端

每次编译、运行和 SPJ 都启动一个一次性容器，并使用：

```text
--rm
--interactive
--name=<random name>
--network=none
--memory=<effective limit>
--memory-swap=<effective limit>
--cpus=1
--pids-limit=64
--cap-drop=ALL
--security-opt=no-new-privileges
--read-only
--tmpfs=/tmp:rw,noexec,nosuid,size=32m
--user=65534:65534
```

只把单次任务临时目录挂载到 `/workspace`。不会把 Docker socket 挂入 API 容器，因为该
socket 等价于宿主 root 权限。超时、输出洪泛、任务取消或监控异常会根据随机容器名执行
额外清理，避免只杀死 Docker 客户端后容器仍在后台运行。

## 已知边界

- JSON 文件锁只保证单个 API 进程内的一致性；不要用多个 Uvicorn worker 共享同一目录。
- Docker 镜像应定期更新并在课程 Linux 环境预先构建。
- 静态 SPJ 检查不能替代沙箱；运行不可信 SPJ 时必须启用 Docker。
- 当前系统面向课程实验，不包含 HTTPS 终止、CSRF token、分布式队列或数据库级事务。
