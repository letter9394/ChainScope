# PostgreSQL 备份与恢复边界

ChainScope 的账号页 JSON 导出仅包含单个用户的数据，不能代替 PostgreSQL 全库备份。Render 免费数据库可能到期；迁移或续期前应保存一份完整的 `pg_dump -Fc` 归档，并把归档和同名 `.sha256` 文件一起保存在受保护、非临时的位置。归档含账户及邮件等敏感数据，不要上传到公开仓库或聊天窗口。

## 已完成的迁移备份

2026-10-13 在暂停应用写入后，从 Render `chainscope-db` 取得最终完整归档；本机核对 SHA-256、11 张表和全部表数据条目，并恢复到 Neon 核对每张表的行数，总计 50 行。随后线上 `DATABASE_URL` 切换到 Neon 新加坡 `production` 分支，健康检查通过；用户已看到历史预警并确认了一条预警。临时备份运行器 IP 规则已移除。旧 Render 库暂时保留以备回退；它是迁移时的快照，**不会同步 Neon 切换后的新写入**。实际归档与密钥位置由管理员私下保存，不应记录在公开仓库。

## 本机离线复查

在仓库根目录运行（替换为要核对的归档路径）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-postgres-backup.ps1 -ArchivePath 'C:\private-backups\chainscope-db-YYYYMMDD-HHMMSS.dump'
```

脚本会比对同名 `.sha256` 文件、读取归档目录，并解压表数据到 Windows 空设备 `NUL`。它不会连接生产数据库、显示表内容或新建本地数据库。它需要仓库 `.tools\postgresql-client` 中的 PostgreSQL 18 `pg_restore.exe`。

## 真正恢复前

完整恢复演练应在**独立的非生产 PostgreSQL 数据库**进行：先确认目标连接、版本、权限和容量，再用 `pg_restore --no-owner --no-acl --exit-on-error` 恢复，核对迁移版本、表数量和关键数据行数，最后仅在确认目标为测试库后清理。不要对生产 Neon 或旧 `chainscope-db` 运行带 `--clean` 或 `--create` 的恢复命令。恢复所需连接信息应通过密码管理器或本机隐藏输入提供，不应写进仓库或命令历史。

## Neon 生产数据库的持续备份

迁移用的 GitHub Actions 工作流仅备份旧 Render 库，**不会**备份现在的 Neon 生产库。新的 `.github/workflows/neon-production-backup.yml` 每天北京时间约 03:17 自动运行，也可在 GitHub Actions 中手动运行。GitHub 定时任务可能延迟；公开仓库连续 60 天没有活动时，定时工作流可能被停用，因此要定期核对最近一次成功记录。

工作流使用已保存在 GitHub Actions Secrets 中的 Neon direct URL 和 32 字节备份密钥；连接时强制验证服务器证书及通道绑定。它先 `pg_dump -Fc`，完整读取归档，然后在运行器上的临时 PostgreSQL 18 中真实恢复并检查表数。全部通过后才生成 AES-256-GCM 加密归档和包含 SHA-256 的清单；只上传密文与清单。第二个独立任务会重新下载上传的文件，认证解密，并在断网的临时 PostgreSQL 18 中再次真实恢复、核对关键表及迁移版本；这两个任务都成功，才算本次备份成功。明文和临时数据库随运行器销毁。归档超过 30 MiB 时安全失败，需先评估 GitHub 免费存储额度再调整上限。

GitHub 产物按加密归档大小自动保留：不超过 0.5 MiB 保留 90 天，不超过 3 MiB 保留 30 天，不超过 12 MiB 保留 7 天，更大但仍在 30 MiB 备份上限内的归档保留 3 天。按每天一份估算，这些档位的理论存储上限合计约 309 MiB；GitHub Free 的 500 MB 额度还会被账号下的其他 Actions 产物和 Packages 共用，手动多次运行也会增加占用。**这不是永久离线备份，也不能代替账号级费用保护。**至少每周下载一份成功运行的加密归档和同次运行的清单，保存在受保护且与此电脑分开的地方；备份密钥也必须另行保管，不能只依赖本机 DPAPI 文件或不可读回的 GitHub Secret。下载文件不可上传到公开仓库、发到聊天，或与密钥放在同一公开位置。在原 Windows 账户上，可用本机 DPAPI 密钥进行不显示密钥的离线验证；脚本会清理临时明文：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-downloaded-neon-backup.ps1 -EncryptedPath '<加密归档路径>' -ManifestPath '<同次运行的清单路径>'
```

若需要保留明文用于独立测试库恢复，才手动在受保护目录解密：

```powershell
# 先通过安全方式在当前 PowerShell 会话中提供 CHAINSCOPE_MIGRATION_KEY_B64。
node .\scripts\decrypt-neon-backup.mjs '<加密归档路径>' '<同次运行的清单路径>' '<受保护的输出路径>.dump'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-postgres-backup.ps1 -ArchivePath '<受保护的输出路径>.dump'
```

解密会产生含个人数据的明文归档，应仅放在受保护的本地目录。脚本不会覆盖已有文件。正式故障恢复时，先在新的空测试数据库恢复最新可用归档，核对账户、规则、事件和迁移版本，再安排停写与切换；**绝不把旧迁移快照或每日备份直接覆盖仍在写入的生产 Neon**。旧 Render 免费数据库预计 2026-10-21 到期，不能把它当长期回退方案。Neon 免费档的短时即时恢复也不能代替这些独立备份。

## 每周异地留存清单

1. 在 GitHub Actions 的 **ChainScope daily encrypted Neon backup** 中，选最近一次两个任务（`encrypted-backup`、`verify-published-backup`）均成功的运行。
2. 下载该次运行的加密归档及同次清单，核对清单中的 SHA-256；只保存密文，绝不把明文归档放入公开仓库或聊天。
3. 把密文和清单复制到受保护的另一台设备或独立存储位置，并确认能够重新读取。GitHub 产物会到期，本机单份也不是异地备份。
4. 由原 Windows 账户持有人通过可信的密码管理器或离线介质另行保管解密密钥，和密文分开放置；不要通过聊天发送密钥。只保存 GitHub Secret 或本机 DPAPI 文件，不能保证未来可恢复。

## 无登录、只读的线上验收

`.github/workflows/production-smoke.yml` 每天北京时间约 05:17 检查公开 `/api/health`、首页和 `/api/auth/csrf`。它只发 GET 请求，不登录、不创建测试预警、不触碰真实用户记录。免费 Web Service 冷启动或 GitHub 定时延迟可能发生，因此脚本先重试，再将持续异常标记为失败；它不会因为一次慢响应就判定生产故障。可在 GitHub Actions 手动运行同一工作流进行复查。Codex 监控只在持续失败、定时任务停用或长时间没有成功运行时提醒；正常时保持安静。登录后的数据隔离与预警业务仍由自动化测试及用户验收覆盖，公开探针不能替代它们。
