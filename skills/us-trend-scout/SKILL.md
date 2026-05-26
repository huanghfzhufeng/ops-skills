---
name: us-trend-scout
description: 美区 TikTok 热点抓取 + 26 数字角色创意配对。每天用 5 路并行 web search 抓美区前一天 5 大细分趋势（时尚/美妆/健康/科技/文化），筛 5 条配对 26 个数字角色出具体创意，加文化情绪总结，输出中文纯文本简报到对话，推送飞书（feishu_webhook_trend，富文本卡片）。v4.8.0 起 viral 挑战 Top 3 迁移到 tk-template-scout 避免重复。触发：用户说"热点日报"、"美区热点"、"us trend"、"trend scout"、"跑一次热点"，或被 /schedule 定时触发。
---

# US Trend Scout

抓美区 TikTok 热点 + 26 数字角色创意配对，作为选题灵感。每天北京时间 9:00 自动跑（= 美东前一天晚上 8-9 点）。

简报**直接 dump 到对话**给运营看（飞书推送功能已下线，未来视需求恢复）。

## 首次使用

无需任何配置即可使用。

**想自定义 26 个数字角色**（可选）：

```bash
mkdir -p ~/.config/ops-skills
cp <skill-dir>/personas.yaml ~/.config/ops-skills/personas.yaml
$EDITOR ~/.config/ops-skills/personas.yaml
```

跨 plugin 升级保留。

## 工作流（按顺序执行）

### Step 1 - 读 personas.yaml

按以下顺序加载数字角色定义：

1. 优先读 `~/.config/ops-skills/personas.yaml`（用户自定义）
2. 找不到则 fallback 到本 skill 目录下的 `personas.yaml`（plugin 自带 26 角色默认）

```bash
USER_PERSONAS="$HOME/.config/ops-skills/personas.yaml"
[ -f "$USER_PERSONAS" ] && PERSONAS="$USER_PERSONAS" || PERSONAS="<skill-dir>/personas.yaml"
```

### Step 2 - 算日期

用 Bash `date` 拿当前北京时间。美东日期 = 北京日期 - 1（早 9 点北京 = 美东前一天晚上 8-9 点）。简报日期格式："5月20日（周三）"。

### Step 3 - 并行 5 路 WebSearch（v4.8.0：去重 viral 挑战块，迁移到 tk-template-scout）

**核心原则（v4.6.0 关键修正）**：query 是渔网不是刀。**广 → 严 → 具**三层漏斗：

```
Step 3 query 层（广）：抽象趋势词 + 时间 + 地区 + 平台，不预设答案
   ↓
Step 4 筛选层（严）：在搜索结果里挑具体可证实的（产品/服务/数字/YoY）
   ↓
Step 5 配对层（具）：基于人设的具体仿拍 brief
```

**绝对禁止**：
- ❌ 不要 hardcode 公司名（如 `Anthropic Meta Microsoft`）→ 把已知答案当 query
- ❌ 不要 hardcode 例子名（如 `like ice bucket Korean baseball`）→ 引导回声室
- ❌ 不要 hardcode 产品类型（如 `service treatment` / `product launch`）→ 切碎信号空间
- ❌ 不要 hardcode 挑战形态（如 `dance / format / meme`）→ 算法权重偏向第一个
- ❌ **不要 hardcode "排除"什么**（如 `non-dance`）→ 这也是预设偏好，是 hardcode 的反向版本

**只用**：类目 + 时间 + 地区 + 平台 + 抽象趋势词（cross-niche / participatory / cultural moment / shift / movement / phenomenon / surge / behavioral）

**v4.6.0 关键修正**：之前用 `non-dance` 排除舞蹈是另一种回声室——把已知答案的反面当作 query。正确做法是**中性 query 让 viral 程度自己排序**，舞蹈和非舞蹈一视同仁，最后看谁真火、谁真跨圈层、谁真能仿。

**5 路 query 模板**（{date} 替换为美东日期 `May 25 2026`）：

```
📊 5 大细分趋势（5 路，只锚类目 + 抽象趋势词）：
1. US fashion industry shift movement {date} 2026 emerging
2. US beauty industry trend movement {date} 2026 YoY surge
3. US health wellness habit shift {date} 2026 viral movement
4. US tech industry structural shift {date} 2026 workforce
5. US Gen Z cultural shift {date} 2026 behavioral
```

**v4.8.0 关键变更**：原 Step 3 第 1-3 路（viral 挑战 cross-niche）已迁移到 `tk-template-scout/SKILL.md` Step 0，由 grab_viral_challenges.py 用真实点赞 + 时间窗硬过滤自动排序。**两个 skill 同一天跑，挑战块只在 TK 模板日推出现，避免重复**。本 skill 只保留 5 大细分趋势 + 文化情绪。

### Step 4 - 筛热点（v4.8.0：只保留 5 大细分趋势，挑战已迁移到 tk-template-scout）

```
👗 时尚 → query 1
💄 美妆 → query 2
💪 健康 → query 3
📱 科技 → query 4（行业 + AI + 大事件）
🌊 文化 → query 5
```

每类只挑**最具趋势性**的 1 条。**筛选标准**：

- ✅ 保留：
  - 服务搜索爆发（如"Korean lash lift YoY +20,082%"）
  - 行业大事件（如"科技公司大裁员"、"AI 训练荒"）
  - 风格主流化（如"trad wife aesthetic 进入 vogue 报道"）
  - 新研究 / 新现象（如"日式间歇步行法"）
- ❌ 排除：
  - 单品发布（如"The Ordinary 出多肽精华"）→ 这是产品，不是趋势
  - 测评类内容（"X vs Y 对比"）
  - 泛言（"AI 火了"、"健康话题受关注"）
  - 去年 / 月度长趋势

### Step 5 - 配对人设（v4.6.0：5 大赛道映射，加时尚）

每条趋势配 **1-2 个**最合适的数字角色：
- **👗 时尚** → Sophie / Ava / Ezra / Riley / Silver / Nari / Jade / Avery
- **💄 美妆** → Ava / Sophie / Nari / Clara
- **💪 健康** → Clara / Leila / Ryan / Max / Avery / Joey
- **📱 科技** → Mia / Charlotte / Priya / Ro / Spencer / Ryan
- **🌊 文化** → Eleanor / Iris / Leo / Caden / Mason / Kai / Jesse / Emma / Jade

每个创意必须**具体**（场景 + 动作 + 钩子），不是"拍个 vlog"。参考示例：
- `Sophie 拍 "策展女孩 1 句 quiet luxury hot take"，西村画廊门口取景`
- `Ryan 拍 "湾区 SWE bro 看 5 月集体裁员的 4 个生存技巧"`
- `Ava 拍 "LA PR 大美女带客户走 Cannes 红毯的 backstage"`

确保 26 个角色在简报里有合理覆盖度（不要 5 条都配同一个 Caden）。

### Step 6 - 拼简报（v4.8.0：5 大细分趋势 + 文化情绪 + 来源链接）

按下方"输出格式"，**markdown 富文本**（飞书 card 渲染 `**加粗**` / `[文字](url)` 链接）。

**关键顺序**：
1. **5 大细分趋势**（时尚 / 美妆 / 健康 / 科技 / 文化，每类 1 条）
2. **文化情绪**（1 段底层观察）

**v4.8.0 强制要求 — 每条细分趋势必须带 1-2 个来源链接**：
- 链接放在「玩法/趋势描述」段后面、「人设配对」前面，单独一行
- 格式：`来源：[标题简短](url) | [标题简短](url)`
- 来源选 Step 3 五路 WebSearch 返回的权威 source（行业报告 / 主流媒体），不要随便贴 medium / 个人博客
- 数字 / 百分比 / YoY 这类**必须有出处**，避免 Claude 编造

注：viral 挑战 Top 3 由 tk-template-scout 推到 template webhook，本 skill 不再输出避免重复。

### Step 7.5 - 推飞书（v4.5.0 复活）

`~/.config/ops-skills/tk-template-scout.yaml` 存了双 webhook（与 tk-template-scout 共用配置文件）：

```yaml
feishu_webhook_trend: "https://open.feishu.cn/open-apis/bot/v2/hook/...."
feishu_webhook_template: "https://open.feishu.cn/open-apis/bot/v2/hook/...."
```

us-trend-scout 推 `feishu_webhook_trend`（v4.8.0 改用 `push_feishu_card.py`，富文本卡片，
能渲染 `**加粗**` / 链接 / emoji 标题，**这是修 v4.6.0 飞书显示 `**xxx**` 没加粗的方案**）：

```bash
WEBHOOK=$(grep '^feishu_webhook_trend:' ~/.config/ops-skills/tk-template-scout.yaml | sed 's/^feishu_webhook_trend: *"\(.*\)"$/\1/')

if [ -z "$WEBHOOK" ] || [[ "$WEBHOOK" == *xxxxx* ]]; then
  echo "skip 飞书推送：webhook_trend 未配置"
else
  # 共用 tk-template-scout 目录下的 push_feishu_card.py
  python3 <plugin-root>/skills/tk-template-scout/push_feishu_card.py \
    --briefing briefing.txt \
    --webhook "$WEBHOOK"
fi
```

返回非 `code:0` → 退出码 1，简报继续 dump 对话。

### Step 8 - 输出 + 报告

把整份简报**直接 dump 到对话**给用户看。然后简要报告：
- 简报字符数
- 8 路 search 成功率
- 可蹭趋势条数（3-5）+ 细分趋势条数（5）
- 涉及人物数
- 飞书推送状态码（如配置）

---

## 输出格式（v4.8.0：5 类细分 + 文化情绪 + 来源链接）

每条细分趋势 3 行结构：① 趋势描述（**带加粗**和**具体数字**）② 来源（1-2 个 markdown 链接）③ 人设配对。

```
美区热点日报 | 5月20日（周三）

📊 细分趋势

👗 时尚
trad wife aesthetic 主流化（从小众回潮到 vogue 报道）
人设配对：Leila 拍"trad wife 一周生活全实拍 vs 主流叙事"，Avery 拍"LA 网红尝试 trad wife 一周记"

💄 美妆
Korean lash lift 搜索量 YoY +20,082%（取代传统嫁接）
人设配对：Nari 拍"ABG 销售 Korean vs 传统 lash lift 哭笑对比"，Clara 拍"护士姐姐解释科学差异"

💪 健康
日式间歇步行法（4 min 快 + 3 min 慢循环替代健身房）
人设配对：Max 拍"湾区 SWE bro 一周试 vs 健身房 PK"

📱 科技
Meta / Anthropic / 微软 5 月集体 AI 裁员潮
人设配对：Ryan 拍"湾区 SWE bro 看 5 月集体裁员的 4 个生存技巧"，Ro 拍"PM 视角的 AI 替人时间线"

🌊 文化
"2026 is the new 2016" 数字纯真回归（反 AI 内容 + 怀念 Snapchat 滤镜）
人设配对：Riley 拍"布鲁克林古着女孩复刻 2016 King Kylie glam"，Nari 拍"ABG 销售翻 2016 自拍"

文化情绪
Gen Z 在"想 IRL 但又离不开 feed"的撕裂里，反 polished 创作者，对小博主真实感的信任度反超大品牌。
```

**赛道 emoji**：👗 时尚 / 💄 美妆 / 💪 健康 / 📱 科技 / 🌊 文化

## 文体约束

- 全中文。专有名词（TikTok / Gen Z / hashtag / sound）保留英文
- **不用 em dash（—）**，用逗号、句号、冒号
- **v4.8.0 起用 markdown 富文本**（飞书 card 渲染）：允许 `**加粗**` 突出数字/百分比/趋势名、`[文字](url)` 链接
- 每条热点结构 3 行：emoji + 趋势描述（带数字）、来源链接行、人设配对行
- 数字角色名首字母大写（Caden / Sophie），不写 handle
- **来源链接强制**：每条趋势至少 1 个权威源（行业报告 / 主流媒体），数字 / YoY 必须可追溯

## /schedule 自动化

每天北京 9:00 自动跑（用户在终端跑，本 skill 不调）：

```
/schedule create "0 1 * * *" "run skill us-trend-scout"
```

UTC 01:00 = 北京 09:00（美东前一天晚上）。

## 失败处理

- WebSearch 失败：retry 1 次。仍失败 → 用剩下成功的几路 + 在报告里标 "X/6 路成功"
- personas.yaml 缺失：明确报错路径 + 提示去补
