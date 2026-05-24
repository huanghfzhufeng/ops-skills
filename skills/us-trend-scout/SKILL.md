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

### Step 3 - 并行 6 路 WebSearch

**6 个 WebSearch 调用必须在同一个 message 里并行发**（不能串行，否则慢 6 倍）。query 模板（{date} 替换为美东日期，格式 `May 20 2026`）：

1. `US trending health wellness clean eating TikTok {date} viral today`
2. `US beauty skincare trending TikTok {date} viral today`
3. `US fitness gym protein trending TikTok {date} today`
4. `US tech AI gadgets trending {date} viral today TikTok`
5. `what's trending on TikTok today {date} US sound audio format`
6. `trending topics {date} US culture viral Gen Z social media moment`

### Step 4 - 筛 5-8 条热点

从 6 路搜索结果里筛**具体可证实**的热点：
- 保留：产品名（"The Ordinary 多肽精华"）、格式名（"And Emily... that's all"）、现象名（"高蛋白甜点品类爆发"）、新研究（"日式间歇步行法"）
- 排除：泛言（"AI 火了"、"健康话题受关注"、"短视频是趋势"）
- 排除：去年/月度长趋势（要"当日/过去几天"颗粒度）

### Step 5 - 配对人设

每条热点配 **1-2 个**最合适的数字角色，按赛道映射：
- 健康/健身/成分 → Clara / Leila / Ryan / Max / Avery / Joey
- 穿搭/彩妆/护肤 → Sophie / Ava / Ezra / Riley / Silver / Nari
- 数码/AI 工具 → Mia / Charlotte / Priya / Ro / Spencer
- 泛娱乐/情绪共鸣（万能型）→ Eleanor / Iris / Leo / Caden / Mason / Kai / Jesse / Emma / Jade

每个创意必须**具体**（场景 + 动作 + 钩子），不是"拍个 vlog"。参考示例：
- `Caden 拍 "高中熬夜赶 essay 时连嗑 5 个蛋白甜品的实测反应"`
- `Sophie 拍 "$30 vs $300 的睫毛精华，纽约策展女孩的诚实测评"`
- `Max 拍 "湾区 SWE bro 试一周日式间歇步行能不能替代健身房"`

确保 26 个角色在简报里有合理覆盖度（不要 5 条都配同一个 Caden）。

### Step 6 - 平台趋势 + 文化情绪

- **本周可蹭趋势**：1-2 条 TikTok 当下热门格式 / sound（格式名 + 玩法 + 适配的 3-4 个人设）
- **文化情绪**：1 句 Gen Z / 时代情绪观察（不是热点，是底层情绪）

### Step 7 - 拼简报

按下方"输出格式"，**纯文本，无 markdown 符号**。

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
- 6 路 search 全部成功 / 几路失败
- 热点条数
- 涉及人物数
- 飞书推送状态码（如配置）

---

## 输出格式（纯文本）

```
美区热点日报 | 5月20日（周三）

🔬 红外光眼罩戴出门
眼部红光疗法穿戴化，像眼镜一样戴出门减黑眼圈，wellness gadget 出圈。
人设配对：Clara 拍 "夜班护士想偷懒 24/7 戴这个能省下我的医美预算吗"，Charlotte 拍 "PM 一天 12 小时盯屏幕，下班 commute 顺便护肤"

💄 The Ordinary 多肽睫毛精华
平价线推出促真睫毛生长的精华，反响"10/10"。
人设配对：Ava 拍 "LA PR 大美女连打卡 3 周 vs Lash Lift 对比"，Sophie 拍 "$30 vs $300 睫毛精华，纽约策展女孩的诚实测评"

（重复 5-8 条）

本周可蹭趋势

"And Emily... that's all"（Miranda Priestly 对比格式）：两件事强对比，适合 Eleanor、Iris、Ezra

文化情绪
Gen Z 在"想 IRL 但又离不开 feed"的撕裂里，开始反 polished 创作者，对小博主真实感的信任度反超大品牌。
```

赛道 emoji：健康 🔬 / 美妆 💄 / 健身 💪 / 科技 📱 / 平台 🎵 / 文化 🌊

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
