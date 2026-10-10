# 台股多周期筛选器

针对台湾上市、上柜股票的盘后技术指标筛选网页。页面可以调整均线、KD、MACD、RSI、DMI规则，并提供严格、宽松两种筛选方式。

## 已保留的功能

- 产业族群多选。
- 严格、宽松筛选模式。
- 均线多头排列与连续向上可分别开关。
- 60分钟、日、月KD可分别设置最近1～10根K线内金叉。
- MACD与DMI可设置最近1～10个交易日；RSI上限可调整。
- 当前规则可以保存为个人策略，保存在当前浏览器中。
- 结果采用卡片布局，手机和平板无需左右滑动。
- 自选股票名单仍可增删；免费网页只能筛选最近一次盘后资料中已有的股票。

## 两种运行方式

### 免费网页模式

GitHub Actions在台湾时间周一至周五16:30自动抓取资料、计算指标，再发布到GitHub Pages。调整页面规则时只会重新筛选已经计算好的结果，所以速度较快。

资料来源：

- 上市、上柜公司清单：TWSE与TPEx公开资料。
- 历史日线与60分钟线：Yahoo Finance非正式公开接口。

Yahoo Finance可能限速、缺漏或改变接口。自动更新设置了成功率保护：成功率低于75%时停止发布，保留前一个正常网页。

### 本机模式

双击`启动Demo.command`，或执行：

```bash
python3 server.py
```

浏览器打开 <http://127.0.0.1:8765>。本机临时扫描最多100档，主要用于测试；完整市场使用盘后网页资料。

## 免费发布到GitHub Pages

项目已经包含`.github/workflows/update-market-data.yml`。上传到GitHub后：

1. 在仓库的`Settings → Pages`中，把来源选择为`GitHub Actions`。
2. 打开`Actions → 更新台股资料并发布网页`。
3. 第一次按`Run workflow`手动运行。
4. 成功后会得到`https://账号.github.io/仓库名/`形式的网址。

以后交易日会自动更新，不需要每天操作。公开仓库不要放API密钥、密码、券商账号或个人资料。

## 本地生成静态资料

先用少量股票验证：

```bash
python3 scripts/update_static_data.py --limit 10 --workers 2 --minimum-success-rate 0.5
```

生成完整市场：

```bash
python3 scripts/update_static_data.py --workers 6 --minimum-success-rate 0.75
```

生成资料位于`static/data/`。网页不会扫描电脑硬盘，也不会读取其他文件。

## 数据口径

- 盘中不采用尚未结束的日K。
- 60分钟KD只使用已完成的60分钟K线。
- 月KD不采用本月尚未完成的月K。
- MACD为12、26、9；RSI为Wilder RSI14；KD为9周期平滑KD。
- 当前使用原始价格，除权息可能形成假信号。
- 成交金额低于5,000万元只显示流动性提醒，不直接排除。

本工具仅整理公开资料，不预测涨跌，不自动下单，也不构成投资建议。
