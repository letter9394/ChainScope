# PostgreSQL 备份与恢复边界

ChainScope 的账号页 JSON 导出仅包含单个用户的数据，不能代替 PostgreSQL 全库备份。Render 免费数据库可能到期；迁移或续期前应保存一份完整的 `pg_dump -Fc` 归档，并把归档和同名 `.sha256` 文件一起保存在受保护、非临时的位置。归档含账户及邮件等敏感数据，不要上传到公开仓库或聊天窗口。

## 已完成的一次备份

2026-10-08 已从 Render `chainscope-db` 导出自定义格式归档，并在本机核对 SHA-256、归档目录与表数据可解压。随后关闭了为备份临时开放的 PostgreSQL 公网 IP 规则。**尚未在独立 PostgreSQL 实例上执行完整恢复演练**，因此不能把离线检查等同于恢复成功。实际归档位置由管理员私下保存，不应记录在公开仓库。

## 本机离线复查

在仓库根目录运行（替换为要核对的归档路径）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-postgres-backup.ps1 -ArchivePath 'C:\private-backups\chainscope-db-YYYYMMDD-HHMMSS.dump'
```

脚本会比对同名 `.sha256` 文件、读取归档目录，并解压表数据到 Windows 空设备 `NUL`。它不会连接生产数据库、显示表内容或新建本地数据库。它需要仓库 `.tools\postgresql-client` 中的 PostgreSQL 18 `pg_restore.exe`。

## 真正恢复前

完整恢复演练应在**独立的非生产 PostgreSQL 数据库**进行：先确认目标连接、版本、权限和容量，再用 `pg_restore --no-owner --no-acl --exit-on-error` 恢复，核对迁移版本、表数量和关键数据行数，最后仅在确认目标为测试库后清理。不要对 `chainscope-db` 运行带 `--clean` 或 `--create` 的恢复命令。恢复所需连接信息应通过密码管理器或本机隐藏输入提供，不应写进仓库或命令历史。
