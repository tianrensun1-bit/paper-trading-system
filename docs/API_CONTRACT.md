# 官方字段与阶段1验证

核对来源：[官方客户端](https://github.com/GMGNAI/gmgn-skills/blob/4575ef539e6a3115fa0481d41285cb79e77970bf/src/client/OpenApiClient.ts)、[市场文档](https://github.com/GMGNAI/gmgn-skills/blob/4575ef539e6a3115fa0481d41285cb79e77970bf/skills/gmgn-market/SKILL.md)、[币信息文档](https://github.com/GMGNAI/gmgn-skills/blob/4575ef539e6a3115fa0481d41285cb79e77970bf/skills/gmgn-token/SKILL.md)。固定官方gmgn-cli 1.6.6，Node 22，Python仅标准库。

|用途|官方接口|使用字段与限制|
|---|---|---|
|热搜|POST /v1/market/hot_searches|params平铺chain/interval/limit/min_marketcap/max_marketcap/min_created；返回chain、interval、tokens；按Mint验证重复，不按位置匹配|
|窗口统计|GET /v1/token/info|price.price、price.price_6h、price.price_24h；收益按价格比计算；volume/buy_volume/sell_volume带6h/24h后缀，USD|
|市值与币龄|同上|price.price×circulating_supply；creation_timestamp为创建Unix秒，不以open_timestamp替代|
|分钟路径|GET /v1/market/token_kline|CLI输入from/to秒后内部转换毫秒；响应时间需验证秒/毫秒；此前实测100根截断，因此每页最多90分钟|

普通只读接口使用X-APIKEY、timestamp与client_id，无私钥签名。CLI运行于空的HOME/cwd，不继承GMGN_PRIVATE_KEY、GMGN_DEBUG或个人配置。只允许热搜、币信息、K线三种读取命令；无swap/order路径。

历史实测显示K线time与文档秒单位不一致，可能返回毫秒；volume/amount的USD解释也与文档相冲突。适配器显式转换时间并保留原单位，成交量两个字段仅保留raw值，不用于USD量价计算。新Key的实际结果尚待本仓库在线复验。

每Mint的6h/24h来自同一次token-info，不受该币是否仍在24h热搜榜影响。不同Mint仍是依次采集；采集跨度被记录，不能声称全市场严格同时。API未提供已验证的统一窗口截止点，因此确认18h值为空，数学暂算值另存provisional字段，不用于资格判断。币龄不足24h时完整24h/前18h收益不可用。

## Secret与实际验证

先撤销聊天中出现的旧Key，在GitHub Actions Secret中设置新GMGN_API_KEY，勿发到聊天或写本机文件。用户确认轮换后，部署步骤设置仓库变量GMGN_KEY_ROTATION_CONFIRMED=true。此变量是操作确认门禁，不是系统能独立证明GMGN旧Key撤销的凭据。

在线命令：`python -m unittest discover -s tests -p test_live.py -v`，需要RUN_LIVE_TESTS=1、Secret及轮换确认。正式扫描前必须在线验证通过；字段存在和请求时间接近不能证明未提供的服务端as-of时间。

只有实际认证、热搜读取、有效snapshot.json.gz和运行日志均可核查，才记录阶段1完成。当前没有这份新密钥证据。
