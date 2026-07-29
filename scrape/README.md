# scrape
独立爬虫项目，用于抓取外部公开页面并生成各业务数据项目的种子文件。

## 运行依赖
- `curl-cffi`：执行 HTTP 请求和浏览器指纹模拟。
- `scrapling`：解析 HTML 页面并提供 CSS 选择器能力。

## 懒人听书种子爬取
运行命令：

```bash
uv run python lrts_seed_crawler.py --max-list-pages 20 --max-items 240 --max-track-pages 0 --delay 0.2
```

默认输出目录：

```text
../audio-data/seeds
```

可通过 `--output-root` 指定其他 `audio-data` 项目根目录。

## 金融业务种子爬取
运行命令：

```bash
uv run python finance/finance_seed_crawler.py --output-root ../finance-data --delay 0.2
```

默认输出目录：

```text
../finance-data/seeds
```

脚本会抓取公开金融业务参考页摘要，并生成基础维度、产品配置、风控规则和指标字典种子文件。默认只输出可提交的 CSV 种子文件；如需保留参考页摘要，追加 `--write-raw` 输出到 `seeds/raw`。
