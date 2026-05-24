---
name: us-trend-scout
description: 美区 TikTok 热点抓取 + 26 数字角色创意配对。每天用 6 路并行 web search 抓美区前一天热点（健康/美妆/健身/科技 + 平台格式 + 文化情绪），筛 5-8 条配对 26 个数字角色出具体创意，加平台格式趋势 + 文化情绪，输出中文纯文本简报到对话，v4.5.0 起同时推送飞书（feishu_webhook_trend）。触发：用户说"热点日报"、"美区热点"、"us trend"、"trend scout"、"跑一次热点"，或被 /schedule 定时触发。
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

### Step 3 - 并行 8 路 WebSearch（v4.6.0：抽象化 query，不 hardcode 名词）

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

**只用**：类目 + 时间 + 地区 + 平台 + 抽象趋势词（shift / movement / phenomenon / surge / cultural / behavioral）

**8 路 query 模板**（{date} 替换为美东日期 `May 25 2026`）：

```
🔥 病毒级非舞蹈内容 / 跨赛道趋势（3 路）：
1. TikTok viral non-dance content this week {date} US 2026
2. TikTok non-dance viral {date} cross-niche cultural moment
3. TikTok hottest non-dance trend {date} platform-wide

📊 5 大细分趋势（5 路，只锚类目 + 抽象趋势词）：
4. US fashion industry shift movement {date} 2026 emerging
5. US beauty industry trend movement {date} 2026 YoY surge
6. US health wellness habit shift {date} 2026 viral movement
7. US tech industry structural shift {date} 2026 workforce
8. US Gen Z cultural shift {date} 2026 behavioral
```

**关键锚定词**："**病毒级非舞蹈内容**"（viral non-dance content）—— 这是唯一锚定，
不要拆成 "challenge / format / meme / skit / POV / behavioral / ritual" 一堆类型词
（会把信号空间切碎，且 dance 在搜索引擎里权重过高）。

### Step 4 - 筛热点（v4.6.0：删产品发布，只留趋势级）

**两类硬筛**：

#### A. 本周可蹭趋势（3-5 条，从 query 1/2 找）

跨赛道传播的 viral phenomenon / format / movement。**有具体玩法、有具体名字、26 人都能蹭**。
- ✅ 保留：现象级挑战（如"冰桶挑战"、"韩国棒球应援"）、格式名（如"Hold the moan"、"And Emily that's all"）、sound trend
- ❌ 排除：单品测评、新产品发布

每条格式：
```
[挑战 / 格式名] (英文原名)
玩法：1-2 句描述怎么玩
人设配对：A / B / C（适配的 persona，逗号分隔）
```

#### B. 5 大细分趋势（每类 1 条，共 5 条）

```
👗 时尚 → query 5
💄 美妆 → query 6
💪 健康 → query 7
📱 科技 → query 8（行业 + AI + 大事件）
🌊 文化 → query 3
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

### Step 6 - 拼简报（v4.6.0：可蹭趋势前置）

按下方"输出格式"，**纯文本，无 markdown 符号**。

**关键顺序**：
1. **可蹭趋势 3-5 条**（最前面，最重要）
2. **5 大细分趋势**（时尚 / 美妆 / 健康 / 科技 / 文化）
3. **文化情绪**（1 段底层观察）

### Step 7.5 - 推飞书（v4.5.0 复活）

`~/.config/ops-skills/tk-template-scout.yaml` 存了双 webhook（与 tk-template-scout 共用配置文件）：

```yaml
feishu_webhook_trend: "https://open.feishu.cn/open-apis/bot/v2/hook/...."
feishu_webhook_template: "https://open.feishu.cn/open-apis/bot/v2/hook/...."
```

us-trend-scout 推 `feishu_webhook_trend`：

```bash
WEBHOOK=$(grep '^feishu_webhook_trend:' ~/.config/ops-skills/tk-template-scout.yaml | sed 's/^feishu_webhook_trend: *"\(.*\)"$/\1/')

if [ -z "$WEBHOOK" ] || [[ "$WEBHOOK" == *xxxxx* ]]; then
  echo "skip 飞书推送：webhook_trend 未配置"
else
  python3 -c "
import json
text = open('briefing.txt').read()
print(json.dumps({'msg_type': 'text', 'content': {'text': text}}, ensure_ascii=False))
  " > briefing.json

  RESPONSE=$(curl -sS -X POST "$WEBHOOK" \
    -H "Content-Type: application/json" \
    -d @briefing.json)
  echo "飞书推送响应：$RESPONSE"
fi
```

webhook 返回非 success → 把 response body dump 给用户，简报继续 dump 对话。

### Step 8 - 输出 + 报告

把整份简报**直接 dump 到对话**给用户看。然后简要报告：
- 简报字符数
- 8 路 search 成功率
- 可蹭趋势条数（3-5）+ 细分趋势条数（5）
- 涉及人物数
- 飞书推送状态码（如配置）

---

## 输出格式（v4.6.0：可蹭趋势前置 + 5 类细分）

```
美区热点日报 | 5月20日（周三）

🔥 本周可蹭趋势

1. "Hold the moan" (憋反应对比格式)
玩法：先正式场合表情，再切换私下真实情绪反应，1-2 秒强对比
人设配对：Iris 拍"四大审计姐 partner 面前 vs 桌底"，Caden 拍"高中老师面前 vs 走廊"

2. "韩国棒球应援" (K-pop 风潮 + 观众席手势文化)
玩法：手指挥应援棒做心形 / 比心动作，配 K-pop 主题音乐
人设配对：Nari、Eleanor、Kai

（重复 3-5 条可蹭趋势）

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

**赛道 emoji**：🔥 可蹭趋势 / 👗 时尚 / 💄 美妆 / 💪 健康 / 📱 科技 / 🌊 文化

## 文体约束

- 全中文。专有名词（TikTok / Gen Z / hashtag / sound）保留英文
- **不用 em dash（—）**，用逗号、句号、冒号
- **不用 markdown 格式符号**（不要 `**bold**` / `## header` / `- list`）
- 每条热点开头一个赛道 emoji + 标题，下一行 1-2 句背景，再下一行 "人设配对：..."
- 数字角色名首字母大写（Caden / Sophie），不写 handle

## /schedule 自动化

每天北京 9:00 自动跑（用户在终端跑，本 skill 不调）：

```
/schedule create "0 1 * * *" "run skill us-trend-scout"
```

UTC 01:00 = 北京 09:00（美东前一天晚上）。

## 失败处理

- WebSearch 失败：retry 1 次。仍失败 → 用剩下成功的几路 + 在报告里标 "X/6 路成功"
- personas.yaml 缺失：明确报错路径 + 提示去补
