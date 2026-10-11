# GMGN Supply Edge · 热搜量价研究（只读）

独立的 Solana Meme 币统计研究项目。**不含交易执行、钱包签名或私钥处理。**

数据源固定为 GMGN 官方 `market hot-searches`（不是 Trending），按照：

- Solana
- 市值 **$30,000 至 $2,000,000**
- 上线 / 创建时间至少 **600 分钟**，不限制最大年龄
- **6h** 市值相近（1.25 倍以内）全配对横向比较
- **24h** 归因和之前 **18h** 的非重叠比较
- 分开输出单位换手价格效应、三变量条件异常排名
- 保存历史样本，以防遗漏跌出热搜的代币；后续复测 1h/3h/6h 预测效果

## 首次启用（手机也可以）

仓库已建立，但**生产采集尚未接入个人 GMGN API**。在 GitHub 手机网页版打开：

**Settings → Secrets and variables → Actions → New repository secret**

- Name：`GMGN_API_KEY`
- Value：在 https://gmgn.ai/ai 重新生成的**新 Key**。以前发到聊天里的 Key 请撤销，避免泄露风险。

然后进入 **Actions → GMGN Read-Only Scan → Run workflow**，运行成功后将自动每三小时尝试扫描一次。定时触发可能会延迟，并不保证准时。

**本仓库当前是公开仓库。** 排名、研究报告和历史快照也会公开。**不要**把钱包地址、私人持仓、交易流水或 API Key 放到仓库文件里；如需接入个人持仓，先将仓库改成 Private，再专门做安全隔离。

## 当前版本说明

- `src/scan.py`：只读调用官方 `gmgn-cli`，计算相对效率和条件异常分数，生成 `reports/latest.md`、`reports/latest.csv`、`data/history.jsonl`、`data/latest.json`。
- `.github/workflows/gmgn.yml`：Push 时单元测试；每天 0/3/6/... UTC 时自动运行一次，另可手动运行。使用 GitHub Secrets 和仓库写权限持久保存快照。
- `tests/`：离线单元测试，不依赖 API Key。
- 缺失的字段和不同步的窗口不强行推断；6h 与 24h 数据必须来自同一次服务调用。
- `Price Effect=6h涨幅百分点 / (6h成交额美元/市值美元)` 是筛选启发式，不证明卖盘供给减少或未来盈利。
- 按市场价测算的 3h / 6h 复评**无法代表滑点后的真实交易收益**；1h 必须有额外小时级采样或K线回填，不能用三小时快照冒充。
- 如果持仓没有被安全授权/正确获取，报告必须写明“未覆盖个人持仓”，不能假装读到了。

## 开发与离线测试

```bash
python -m unittest discover -s tests -v
npm install -g gmgn-cli
export GMGN_API_KEY=***    # 仅示意，请勿填入 Git 跟踪文件
gmgn-cli config --check
python src/scan.py
```

官方说明：[GMGN CLI](https://github.com/GMGNAI/gmgn-skills/blob/main/docs/cli-usage.md)。

## 验证标准

**只有 Actions 工作流真实显示了 GMGN 返回的代币数量、6h/24h 字段、来源时间，且生成了一份有效 `reports/latest.md`，才算数据采集打通。** README、代码提交或离线单元测试通过都不代表 API 连接成功。
