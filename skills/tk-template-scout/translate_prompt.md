# Title 翻译 + 仿拍 Brief 生成 Prompt

> v4.5.0 起，tk-template-scout 简报必须含中文化标题 + 仿拍建议。
> 这个步骤由 Claude 主线（不是单独 API）在执行 SKILL.md 时按本 prompt 完成，
> 写入 `translated.json` 给 `render_briefing.py` 渲染。
> 翻译规则代码无法固化，但 prompt 必须严格遵守，保证 70%+ 翻译结果一致性。

## 任务

对 `scout_strict.py` 输出的 `result.json` 里**每条 video**，生成两个新字段：

- `title_cn`：中文化视频标题/描述（20-40 字）
- `fanpai_brief`：基于该 persona 人设的仿拍建议（30 字内）

把这两个字段**加到原 video dict 里**，保留所有原字段（url / like_count / uploader / timestamp / source / view_count / comment_count），保存为 `translated.json`。

## title_cn 规则

**目标**：让运营 1 秒看懂视频在干嘛 + 能不能仿拍。

### 必须遵守
1. **保留英文专有名词**：TikTok / hashtag (#fyp / #ootd) / 品牌（Ferrari / Patek / Nike / Vogue）/ 配乐名 / 地名（NYC / SF / LA / Brooklyn）/ 平台 / 角色名
2. 视频里出现的**金句或核心句**用「」标记
3. 必须标注**视频形式**，从这些里选：vlog / 段子 / 教程 / 拼贴 / unboxing / 测评 / haul / GRWM / OOTD / mukbang / 短片 / 实拍 / cosplay
4. **不要 em dash（—）**，用逗号、句号、冒号
5. **不要 markdown**（不要 `**bold**`、`## header`、`- list`）
6. 长度 **20-40 中文字**（含 hashtag 计字符数）

### 翻译例子（必须模仿）

| 原 title | title_cn |
|---|---|
| Please tell me I'm not the only one? 😅😂 #fyp #viral #funny #momlife | 「告诉我不是只有我这样」宝妈搞笑共鸣段子 |
| Backend SWE Roadmap 2026 This is the roadmap I'd follow to become a b... | 2026 后端 SWE 学习 roadmap（程序员成长路径） |
| Today's free lunch at work! 👩🏻‍💻 😋 #corporatelife #lunch #officelife | 公司免费午餐 vlog（亚裔白领日常段子） |
| The people who feel the most luxurious are rarely trying the hardest | 「真正显得有钱的人，反而不在用力穿」quiet luxury 哲学金句卡片 |
| #y2kaesthetic #2000sfashion #outfitinspo #ootd #grwm | Y2K / 2000 年代风 ootd + GRWM 化妆教程 |
| 2020 vibes aesthetic ᵕ̈ #foryoupage #2020 #viral #vibes2020 #indie | 2020 年 indie vibes aesthetic 怀旧短片 |
| La première promenade dans le paddock @F1GPCanada pour Walter 🏎️🏆 | Walter 第一次进 F1 加拿大站 paddock 现场 vlog（法语） |
| 🔥 Level up your core game! 💪 Here are my top deep core exercises | 升级核心训练：5 个深层 core 动作教程 |

### 不要做什么
- ❌ 不翻译 hashtag（`#fyp` 保留 `#fyp`，不翻成 `#你为页面`）
- ❌ 不加营销话术（"这视频超火！"）
- ❌ 不重复 raw title 的逐字翻译
- ❌ 不凑字数（短就短）

## fanpai_brief 规则

**目标**：给运营 1 行可执行的仿拍 brief（不是泛言）。

### 必须遵守
1. **句首固定**：`<Persona 名> 拍...`
2. 基于 persona 人设的 **城市 / 职业 / 性格** 做改造（从 personas.yaml 的 persona 字段读）
3. 给**具体场景 + 动作 + 钩子**，不要"拍个 vlog"这种泛言
4. 30 字内
5. 用「」标记仿拍的核心句

### 例子（必须模仿）

| Persona | 人设 | 视频内容 | fanpai_brief |
|---|---|---|---|
| Sophie | 西村画廊女孩 NYC 24 岁策展助理 | quiet luxury 金句 | Sophie 拍「策展女孩对 quiet luxury 的 3 句 hot take」西村画廊门口取景 |
| Mia | Tribeca 黑人投资女王 NYC 24 岁 PE | 宝妈搞笑共鸣 | Mia 拍「Tribeca 投资女周末带娃 vs 周一进 office 反差段子」 |
| Ryan | 湾区健身工程师 bro SF 25 岁 SWE | 后端 SWE roadmap | Ryan 拍「湾区 SWE bro 一周打卡 ML 入门 roadmap」家里 setup 取景 |
| Spencer | WASP 纽约科技帅哥 24 岁 PM | F1 paddock | Spencer 拍「PM 周末去蒙特利尔 F1 paddock，穿 Ferrari 周边」 |
| Caden | 搞笑 e 人芝加哥碎嘴高二大男孩 | 高中情侣搞笑 | Caden 拍「高二男生女友锁屏 + 隐私屏的 5 个无奈反应」 |
| Emma | 甜美邻家波士顿 23 岁出版社助理编辑 | 10 分钟芝士汉堡饺子 | Emma 拍「波士顿编辑下班 10 分钟做芝士汉堡饺子配 chai」 |

### 不要做什么
- ❌ 不重复 persona 人设描述（briefing 已经标了 handle，不需要再说"24 岁 NYC 策展助理"）
- ❌ 不要"非常好的模板，建议仿拍"这种空话
- ❌ 不要超过 30 字

## 输出格式（写到 translated.json）

```json
{
  "mode": "...原值不动...",
  "generated_at": ...,
  "personas": {
    "sophie": {
      "videos": [
        {
          "url": "https://www.tiktok.com/@iamshaniakhan/video/7643106369498909966",
          "title": "The people who feel the most luxurious are rarely trying the hardest",
          "title_cn": "「真正显得有钱的人，反而不在用力穿」quiet luxury 哲学金句卡片",
          "fanpai_brief": "Sophie 拍「策展女孩对 quiet luxury 的 3 句 hot take」西村画廊门口取景",
          "like_count": 9641,
          "uploader": "iamshaniakhan",
          "...其他原字段不变...": "..."
        }
      ],
      "...其他 persona 级字段不变...": "..."
    }
  }
}
```

## 失败处理

- 翻译异常（视频 title 太短 / 全是 emoji）：用 raw title 的 emoji + hashtag 简要描述，标 `[原 title 信息不足]`
- 仿拍 brief 想不出场景：给保守版「<Persona> 拍此视频的 <人设场景> 版本」

## 调用方式

Claude 在 SKILL.md Step 6 执行时：
1. 读 `result.json`
2. 读 `personas.yaml` 拿每个 persona 的人设描述
3. 读本 prompt 文件了解规则 + 例子
4. **一次性**翻译所有 video（不要分多次小请求浪费 context）
5. 写 `translated.json`
6. 调 `render_briefing.py --json translated.json`
