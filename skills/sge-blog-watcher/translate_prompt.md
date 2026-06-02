# SGE 博客中文化规则（Claude 主线执行，不调外部 API）

把 `watch.py check` 输出的 `new[]` 数组，逐篇生成中文卡片字段，**一次性**写出
`translated.json`。这一步由 Claude 主线完成（项目惯例：翻译不调外部翻译 API）。

## 输出结构

```json
{
  "posts": [
    {
      "url": "<原样保留>",
      "published": "<原样保留>",
      "section": "<原样保留英文>",
      "read_minutes": 2,
      "title_cn": "...",
      "summary_cn": "...",
      "tldr_lines": ["...", "...", "..."]
    }
  ]
}
```

保留每篇的 `url` / `published` / `section` 原值（render_card.py 用它们排版 +
做分类中文映射）。新增下面 4 个字段。

## 字段规则

### title_cn（中文标题，20–40 字）
- 翻译原 `title`，**保留专有名词英文**：App 名（Studora / Turbo AI）、平台
  （TikTok / Reels）、创作者 handle（@nedatheastrologer）
- **保留关键数字**：播放量、增长（如「11.4M 播放」「30 天」）
- 标题就是卡片 header，要一眼看懂这是什么模版 / 什么案例

### summary_cn（一句话摘要）
- 翻译原 `description`（没有就取正文首句）
- 一句话讲清「这篇在讲什么」，不超过 40 字

### tldr_lines（正文要点，markdown 数组）
**这是运营最看重的部分**——不点开原文就知道这模版怎么用。每行一个要点，
句首用 `**🔑 核心**：` / `**📌 钩子**：` / `**💡 洞察**：` / `**📊 数据**：`
这类加粗小标题。规则：

- **必带具体可复用信息**，不要泛泛而谈：
  - 具体账号 handle（`@rayna_dee 690K 粉`）
  - 具体播放量 / 数据（`一条视频 400 万播放`）
  - **可复用钩子原文**：英文原句 + 中文注解，例如
    `「When you're so locked in you actually start enjoying it」（专注到开始享受）`
    （仿拍要照抄英文，必须保留原文）
- 行数按正文长短：
  - 正文很短（teaser，< 500 字）→ 1–2 行，别硬凑
  - 普通 case study（1–3 千字）→ 3–4 行
  - 深度报告（上万字）→ 4–6 行，挑最硬的数据 / 结论，**不要复述全文**
- **不许编数字**：所有播放量 / 粉丝数必须来自 `body` 或 `description` 原文，
  正文里没有就不写

### read_minutes（整数，可选）
- 从 `read_time_raw`（如 `2 min read` / `< 1 min read`）取整数
- `< 1 min read` → 填 `1`；取不到就省略该字段

## 重要约束
- ❌ 不要分多次小调用逐篇翻译（浪费 context）——一次性读完 new[] 全部生成
- ❌ 不要漏篇：new[] 里每篇都要在 posts[] 里有一条（带 `error` 字段的除外，跳过）
- ❌ 不要在卡片里写「为什么推这篇 / 仿拍建议」——运营要的是「这模版是什么」，
  不是「你该怎么做」（那是 tk-template-scout 的活）
- ✅ 全中文，专有名词 / 钩子原文保留英文
- ✅ 不用 em dash（—），用逗号句号冒号
