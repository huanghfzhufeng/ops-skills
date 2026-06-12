---
name: tk-niche-scout
description: 美区 TikTok 任意赛道 1000+ 爆款链接清单生成器。三渠道找号(种子/榜单站/搜索雪球) → yt-dlp 扫主页硬过滤(2026·≤15s·≥100万·真链接) → 四道净化(跨赛道去重/硬广/账号名/caption信号) → 按粉丝分桶(≤50万=UGC模板置顶,按播放/粉丝比排序)。内置 comedy/beauty/fashion 三套实战验证词典,新赛道写一个 yaml 即可。触发：用户说"跑一个 X 赛道链接清单"、"X 赛道 1000 条链接"、"tk-niche-scout"、"赛道链接清单"、"再做一个 XX 名单"。
---

# TK Niche Scout — 赛道爆款链接清单生成器

一句话：给一个赛道（搞笑/美妆/穿搭/任意），产出 **1000+ 条实测真链接**的爆款短视频清单，
UGC 可仿拍模板置顶，交付 TSV 到 `~/Downloads/`。

2026-06-12 实战战绩：搞笑 1715 条 / 美妆 1227 条 / 时尚 1458 条，合计 4400 条，单赛道 3-6 小时。

## 产出规格（硬标准，写死在 tk_lib.py）

每条链接同时满足：**2026 年发布 · ≤15 秒 · 播放 ≥100 万 · yt-dlp 实测可访问 · 链接级去重**。

交付三件套（`~/Downloads/`）：
| 文件 | 内容 |
|---|---|
| `us_<niche>_tiktok_2026_final_<日期>.tsv` | 9 列主表：bucket / url / views / duration_s / upload_date / creator / followers / views_per_follower / caption |
| `..._links.txt` | 纯链接 |
| `..._removed_....tsv` | 被净化剔除的 + 原因（可回查可捞回） |

分桶：粉丝 ≤50 万 = `UGC模板`（置顶，桶内按 **播放/粉丝比** 降序 = 模板价值排序）；
>50 万 = `名人/大号`（沉底）。比值高 = 火的是格式不是人 = 可仿拍。

## 前置

1. `yt-dlp`、`pip install -r requirements.txt`、`python3 -m patchright install chromium`
2. Chrome 真实登录过 TikTok，cookies 已导出到 `~/.config/ops-skills/tiktok-cookies.txt`
   （必须含 `sessionid`，导出命令见 tk-template-scout SKILL.md；**仅收割器需要**，枚举器免 cookie）

## 开工前必做：对齐四问（血泪教训，跳过会返工）

照抄这套话术跟需求方确认，**每一问都改变词典和净化规则**：

1. **赛道边界**——"X 赛道的范围画在哪？"（实例：美妆=彩妆+护肤，发型美甲算不算？
   穿搭=服装+鞋包配饰，男女装都收？）
2. **UGC 还是大号**——"主要要素人可仿拍模板，还是名人爆款也要？"（决定分桶线 + 排序；
   默认 ≤50 万粉=UGC 置顶、名人沉底不删）
3. **跟既有名单去重吗**——"这批要不要跟之前的 XX 名单去重？"（视频级 URL 去重，
   `--dedup-against` 传先前 final TSV）
4. **硬广容忍度**——"带 #ad/带货话术的要不要？"（美妆/穿搭实战硬广密度高，默认开过滤；
   注意只能抓**明示广告**，未打标签的软性带货看文字判不出来——这是不看视频方案的边界，要提前说清）

## 五步流程

```bash
SKILL=<skill-dir>; NICHE=$SKILL/niches/<name>.yaml; WD=~/.cache/ops-skills/<name>

# ① 收割（两条流并行，各 30 词温和串行；~1-2.5h 视限流）
nohup python3 $SKILL/harvest.py --niche $NICHE --stream 1 > $WD/s1.log 2>&1 &
nohup python3 $SKILL/harvest.py --niche $NICHE --stream 2 > $WD/s2.log 2>&1 &

# ② 大号桶补充：Claude 当场 WebFetch yaml 里 list_sites 的榜单页抠 @handle，
#    人工剔品牌空壳/非美区后，追加进 $WD/celeb_list.txt（autopilot 建好清单后、开扫前都来得及）

# ③④⑤ 总指挥一条龙：等收割 → 枚举(UGC 优先) → 四道净化 → 分桶 → 出货
nohup python3 $SKILL/autopilot.py --niche $NICHE \
  --dedup-against ~/Downloads/us_<先前赛道>_tiktok_2026_final_*.tsv \
  > $WD/autopilot.log 2>&1 &
```

跑前先做 **5 分钟产量小测**（拿 2-3 个该赛道头部号），单号 ≥3 条说明 ≤15s 档成立：

```bash
yt-dlp --skip-download --no-warnings --ignore-errors --playlist-end 200 \
  --dateafter 20260101 --match-filter "view_count>=1000000 & duration<=15" \
  --print "%(id)s" "https://www.tiktok.com/@<头部号>" | wc -l
```

进度随时可出快照给需求方抽查（合并 jsonl → 临时 TSV，参考 autopilot 第 4 步逻辑）。

## 质量保障（回答"凭什么是这个赛道的"）

四道全机器、不看视频：

1. **入口保纯**（最关键）：链接只从该赛道创作者主页产出；号只能从三渠道进池——
   yaml 种子（实战验证过的头部）、榜单站现薅、赛道搜索词雪球。
   逻辑：号是这个赛道的，它的爆款绝大多数就是这个赛道的。
2. **硬指标**：三条硬标准抓取时过一遍、合并时复验一遍。
3. **账号净化**：每号全部 caption 汇总打正负信号分（词典在 yaml），零正信号+有负信号
   或负信号占优 → 整号剔；账号名负词/区域后缀(.de/.ph)/宠物号/黑名单一票否决。
4. **硬广**（可选）：#ad/#sponsored/折扣码话术单条剔，品牌店铺名整号剔。

交付时抽 20 条 yt-dlp 复验（链接活性+数值），实战 20/20；可再随机下载 10 条视频
本体给需求方人工抽查。**诚实边界**：赛道纯度约 90-95%，100% 只有人眼看视频才能给。

## 踩坑库（每条都是实战换来的，别再踩）

| 坑 | 结论 |
|---|---|
| TikTok 搜索页并发 | **单 context 串行 + 2-4s 抖动唯一安全**。4 并发×40 任务 = 几分钟内全员"Page not available"软拦截 + 会话风控升级，且会拖累同 IP 的 yt-dlp |
| hashtag 页(/tag/) | 没下线，但对自动化通过率 ~2.6%（风控选择性软拦截），**别当数据源**，search 页才是活路 |
| yt-dlp 路径 | 扫**主页**稳（3 赛道 ~1900 号零封禁，免 cookie）；打 /tag/ /music/ 聚合页必死("No working app info") |
| 粉丝数 | 单视频 yt-dlp JSON **没有** follower 字段；`curl 主页 HTML` 正则抠 `"followerCount":\d+` 即可，一号一次 |
| 限流自愈 | 失败率 ≥40% 判整体限流 → 退避 60s×轮次重试失败号（≤2 轮），个别失败不等待。实战多轮限流波全部自愈 |
| 工件目录 | **必须 `~/.cache/ops-skills/<niche>/`**，/tmp 重启即清（实战丢过一次半成品） |
| 长活形态 | nohup 后台 + 日志轮询，**绝不前台死等**（600s 被杀）；autopilot 幂等，断了重启接着跑 |
| 生产窗避让 | 08:28-08:55 是 tk 每日定时抓取窗口，重活让路（`--guard-window`，默认开） |
| 榜单站质量 | Feedspot 最干净；TokPortal 杂（品牌空壳+东南亚号多，须人工剔）；heepsy 403 拒爬 |
| 产量预期 | 单号均产 2-7 条；高产是"短格式专业户"（实战最高单号 90 条）；標 ≤15s 在搞笑/美妆/穿搭三赛道都成立，新赛道先小测 |

## 新赛道接入（10 分钟）

复制 `niches/comedy.yaml` 改五块：60 个搜索词（两流各 30，格式向 query 出 UGC）、
榜单站 URL、种子号、caption/handle 正负词典、四个开关
（`ad_filter` 带货密度高的赛道必开，`strict_zero_pos` 仅 caption 带品类词比例高的赛道开——
搞笑这种纯画面梗赛道**不能开**）。跑完先抽查 removed 文件确认没误杀，再调词典。

## 交付话术模板（直接贴群）

> 【X 赛道链接清单·质量说明】
> 这批链接不是人工一条条看视频挑的，靠 N 道自动筛选保证是 X 内容（范围：…）：
> 第一道：只从 X 账号里选视频（来源：榜单站可点链接核对 + 站内搜索 ~N 个词）
> 第二道：只收 2026 年发布、播放超 100 万、15 秒以内、链接实测可打开的
> 第三道：机器通读账号全部文案剔杂号（共清掉 N 个账号、N 条，单独存档可查）
> （第四道：剔硬广 N 条）
> 最终交付：N 条（素人 UGC 模板 N + 头部大号 N），来自 N 个创作者。
