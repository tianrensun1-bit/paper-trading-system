# GMGN Solana 动态量价研究（只读）

研究相似市值 Meme 币的量价响应是否能够预测未来超额收益，以及优势恶化、恢复和独立风险保护是否能改善持仓结果。**当前为阶段1接入修复：未证明新密钥可用，未完成回测或模拟交易，不执行订单。**

研究思想与后续A/B/C/D实验约束见[开发交接](docs/HANDOFF.md)，官方字段与时间局限见[数据契约](docs/API_CONTRACT.md)，真实验证状态见[验证记录](docs/VALIDATION.md)。

## 固定研究范围

- GMGN官方Hot Searches，Solana；不是Trending或新币榜。
- 当前市值30,000–2,000,000 USD；创建币龄至少600分钟，无最大年龄。
- 6h为主，对市值比不超过1.25的所有对手配对。
- 原始Price Effect = 6h收益百分点 / (6h美元成交额/当前美元市值)。上涨币排名与高量少跌分开。
- 条件异常排名独立控制市值、相对成交额、币龄及可用流动性，至少8个参照；仅为描述性稳健统计，没有训练好的预测模型。
- 24h包含6h。只有窗口确实对齐才能确认此前18h的成交额与复合收益；目前官方响应没有可核实的统一截止点，确认值为空，暂算值单独保存。币龄不足24h不拆完整18h。
- 6h和24h来自每个Mint同一次token-info，包括未进入24h榜的6h样本。不同Mint顺序采集，保留逐币接收时间与整体跨度，并非严格同一时刻快照。

所有交易资格暂为WAIT。15m/1h/4h结构、背离确认、再入场和利润保护规则尚待定义与回测；排名不能自动获得买入资格。流动性不足不能证明有效卖盘减少。

## 手机启用与真实验证

此前出现在聊天里的Key必须撤销。请直接在仓库[Actions Secrets设置](https://github.com/tianrensun1-bit/paper-trading-system/settings/secrets/actions)保存新Secret `GMGN_API_KEY`，不要将Key发到聊天或写进文件。确认“新密钥已设置并撤销旧密钥”后，维护者才会把仓库变量 `GMGN_KEY_ROTATION_CONFIRMED` 设为 `true`，启用真实访问。

在[Actions](https://github.com/tianrensun1-bit/paper-trading-system/actions/workflows/gmgn.yml)选择Run workflow。工作流先执行离线测试，再安装锁定的官方gmgn-cli 1.6.6，强制执行真实认证、热搜/字段/K线测试，最后生成实际行情快照。任何真实检查失败都会使运行失败；不会用测试数据作为备用行情。

每3小时的cron为UTC 00:17、03:17、06:17等，GitHub可能延迟或漏过调度。已观察到旧版定时任务触发但因空Key扫描失败；新版定时采集仍待验证。配置不能用于实时风险保护。

成功后在GitHub手机网页阅读[最新中文报告](reports/latest.md)；下载[完整CSV](reports/latest.csv)。报告和CSV会在失败时明确失效，旧快照留在历史目录。

**此仓库目前公开。只提交市场数据。** 个人钱包、持仓及交易流水在私有存储方案明确前不接入；钱包只接受公开地址，永远不请求私钥或助记词。未来Risk Engine不能只依赖每3小时Actions。

## 文件与历史持久化

- `src/contracts.py`：官方响应校验、创建币龄、价格起点收益、美元成交额。
- `src/gmgn_api.py`：仅允许热搜、token-info和K线三个只读命令；隔离本机配置与私钥环境，抑制原始错误输出，保存脱敏响应。
- `src/scan.py`：全配对、原始PE、独立异常、窗口检查、中文报告和完整样本保存。
- `data/runs/<run_id>/`：每次真实运行的压缩原始响应、完整行情快照、全部样本CSV、全部配对CSV、排除记录、报告与运行清单。
- `data/history.jsonl`：追加的快照索引，不删除下跌、退榜或失效样本；当前未实现持续回补这些Mint的未来收益。
- `data/latest.json`、`data/status.json`：最新状态与覆盖率。
- `.github/workflows/gmgn.yml`：手动/定时运行，串行持久化；即使失败也保存状态和已有历史，另保留90天恢复artifact。Git仓库内历史没有artifact过期限制。

API Key只从Actions Secret传入。不继承GMGN私钥或个人CLI配置，不包含交易执行命令。后续实盘必须另行明确授权。

## 本地离线验证

Python运行时只用标准库；pytest仅用于本机测试，CI使用unittest，无额外Python依赖。

```bash
python -m pytest tests -q
python -m unittest discover -s tests -v
```

实际客户端使用固定版本和依赖锁：

```bash
npm ci --ignore-scripts --no-audit --no-fund
```

真实API测试仅在安全环境中已有新Key、轮换确认及显式 `RUN_LIVE_TESTS=1` 时运行：

```bash
python -m unittest discover -s tests -p test_live.py -v
python src/scan.py
```

当前离线结果为24项通过，2项真实API测试跳过。**只有新密钥下真实认证、热搜/字段测试、实际快照与Actions记录都验证成功，阶段1才完成。** 历史回测、MFE/MAE、未来1h/3h/6h检验、全部真实持仓复评与Paper Broker均尚未完成。
