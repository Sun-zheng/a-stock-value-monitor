# AI 引擎与本地配置说明

## 配置文件位置

当前网页系统读取：

- `aiagents-stock-main/.env`

根目录定时/交付脚本可读取：

- `.env`

两个文件都在当前项目目录体系内，且都被 `.gitignore` 忽略。真实密钥只保存在本机，不提交到 GitHub。

## ModelScope 配置项

`.env` 中需要以下变量：

```env
MODELSCOPE_API_KEY=""
MODELSCOPE_BASE_URL="https://api-inference.modelscope.cn/v1"
AI_MODEL_POOL="deepseek-ai/DeepSeek-V4-Flash,stepfun-ai/Step-3.7-Flash,moonshotai/Kimi-K2.7-Code:Moonshot"
```

## 统一调用入口

新功能优先使用：

- `interface/ai/ai_engine.py`
- 类：`AIEngine`

示例：

```python
from interface.ai.ai_engine import AIEngine

response = AIEngine(default_model="deepseek-ai/DeepSeek-V4-Flash").chat(
    messages=[{"role": "user", "content": "你好"}],
    allowed_providers={"modelscope"},
    use_pool=False,
)

if response.ok:
    print(response.content)
```

`DeepSeekClient` 仍保留兼容旧股票、板块和龙虎榜调用，但新代码不要直接散落创建供应商客户端。

## 当前验证结果

连续验证可用于文本复核、建议放入默认轮询池的 ModelScope 模型：

- `deepseek-ai/DeepSeek-V4-Flash`
- `stepfun-ai/Step-3.7-Flash`
- `moonshotai/Kimi-K2.7-Code:Moonshot`

已注册但当前不建议放入默认轮询池：

- `MiniMax/MiniMax-M3`：本地验证时返回余额不足。
- `inclusionAI/Ring-2.6-1T`：本地验证时返回授权无效。
- `ZhipuAI/GLM-5.2`：本地复测时返回 quota 限制。
- `deepseek-ai/DeepSeek-V4-Pro`：本地复测时返回 quota 限制。

## 验证命令

```bash
cd aiagents-stock-main
.venv/bin/python tools/validate_ai_providers.py --models deepseek-ai/DeepSeek-V4-Flash,stepfun-ai/Step-3.7-Flash,moonshotai/Kimi-K2.7-Code:Moonshot --timeout 60
.venv/bin/python tools/test_etf_batch_ai.py --counts 5,10,20 --with-ai --model deepseek-ai/DeepSeek-V4-Flash
```
