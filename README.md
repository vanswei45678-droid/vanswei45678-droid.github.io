# MacroScope Complete v6.0

这是一个可直接发布到 GitHub Pages 的全球宏观与市场看板。压缩包一次性包含：

- 完整程序代码
- 两个 GitHub Actions 工作流
- 所有数据 CSV 文件
- 首次部署不空白的内置演示数据
- 自动真实数据更新脚本
- A股交易拥挤度历史回填工具
- 数据结构验证工具
- 已构建的 `public/index.html`

## 重要说明

压缩包中的初始数据明确标记为“内置演示数据”。它只用于保证首次上传后网页不是空白，不能用于投资决策。首次在 GitHub Actions 运行 `mode: all` 后，成功取得的真实公开数据会自动删除并替换相应演示行。

## 覆盖指标

- M1、M2、M1-M2剪刀差、社融、PMI、CPI
- DR001、DR007、隔夜 Shibor
- 上证综指、深证成指、创业板指、沪深300、科创50、中国科技龙头
- 纳斯达克、标普500、道琼斯、美元指数
- 美国2年和10年期国债收益率
- Apple、Microsoft、NVIDIA、Amazon、Alphabet、Meta、Tesla、Micron
- 三星电子、SK海力士
- A股上涨/下跌/平盘家数、两市成交额、成交额/总市值
- A股两融余额、两融余额/总市值
- A股成交额前5%股票成交额/两市总成交额
- 指数10周和20周均线偏离度
- 指数历史PE/PB
- 新成立基金募集份额与估算募集规模

## 数据文件

`data/` 中完整包含：

- macro.csv
- liquidity.csv
- market.csv
- global_macro.csv
- valuation.csv
- crowding.csv
- breadth.csv
- leverage.csv
- deviation.csv
- fund_subscription.csv
- a_share_universe.csv
- status.json
- manifest.json

## 第一次上线

1. 新建 GitHub Public 仓库。
2. 上传本项目文件夹内部的全部内容，包括 `.github`。
3. Settings → Actions → General → Workflow permissions → Read and write permissions。
4. Settings → Pages → Source → GitHub Actions。
5. Actions → Update data and deploy public dashboard → Run workflow → `mode: all`。
6. 等待绿色对勾后打开 Pages 地址。
7. Actions → Backfill A-share crowding history，先回填最近一个月测试，再回填2025年至今。

详见 `docs/FULL_GITHUB_INSTALL.md`。
