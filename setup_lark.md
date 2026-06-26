# 飞书配置说明

项目使用已经授权的 `lark-cli`，不保存飞书 token、app secret 或 webhook。

检查命令：

```powershell
lark-cli --help
lark-cli auth status
lark-cli doctor
lark-cli base --help
```

当前固定 Base 的标识和链接保存在 `data/feishu_table.json`。不要删除该文件，也不要在日常任务中再次调用 `+base-create`。

手动检查表格：

```powershell
$cfg = Get-Content .\data\feishu_table.json | ConvertFrom-Json
lark-cli base +base-get --base-token $cfg.base_token --as user
lark-cli base +field-list --base-token $cfg.base_token --table-id $cfg.table_id --as user
lark-cli base +record-list --base-token $cfg.base_token --table-id $cfg.table_id --as user
```

若授权过期，先运行 `lark-cli auth status` 和 `lark-cli doctor`。项目不会要求配置新的开放平台应用。

