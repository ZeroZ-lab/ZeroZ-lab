#!/usr/bin/env python3
"""
自动同步头部仓库到 README.md

功能：
  - 调用 GitHub REST API 拉取用户公开仓库
  - 过滤掉 fork 仓库、profile 自身仓库
  - 按 star 数降序，取 Top N（默认 6）
  - 生成卡片网格，注入 README 的 <!--REPOS:START-->~<!--REPOS:END--> 区块

仅依赖 Python 标准库，无需 pip install。
GitHub Action 提供默认 GITHUB_TOKEN 即可运行（免额外配置）。
"""

import json
import os
import sys
import urllib.parse
import urllib.request

# ===== 配置 =====
USERNAME = "ZeroZ-lab"                       # GitHub 用户名
TOP_N = 6                                    # 展示仓库数量
README_FILE = "README.md"                    # 目标文件
START_MARKER = "<!--REPOS:START-->"          # 区块开始标记
END_MARKER = "<!--REPOS:END-->"              # 区块结束标记

# 卡片配色：纯黑文字 + 浅灰背景，契合极简技术风
CARD_BG = "ffffff"
CARD_TITLE = "000000"
CARD_TEXT = "555555"
CARD_ICON = "000000"


def fetch_repos(username: str) -> list:
    """拉取用户全部公开仓库（自动翻页，每页 100 条）。"""
    repos = []
    page = 1
    # 优先使用 GITHUB_TOKEN（Action 环境），未认证时走匿名（60次/小时）
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("MY_GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": username,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    while True:
        url = f"https://api.github.com/users/{username}/repos?per_page=100&page={page}&sort=pushed"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"⚠️  拉取第 {page} 页失败: {e}", file=sys.stderr)
            break

        if not data:  # 空页 = 拉完
            break
        repos.extend(data)
        page += 1
        if page > 10:  # 安全上限：1000 个仓库
            break

    return repos


def select_top_repos(repos: list, username: str, top_n: int) -> list:
    """筛选非 fork、非自身仓库，按 star 降序取前 N。"""
    filtered = []
    for r in repos:
        if r.get("fork"):
            continue
        if r.get("name") == username:  # profile 自身
            continue
        if r.get("archived"):
            continue
        filtered.append(r)

    filtered.sort(key=lambda x: x.get("stargazers_count", 0), reverse=True)
    return filtered[:top_n]


def escape(text: str) -> str:
    """转义 URL 查询参数中的特殊字符。"""
    if not text:
        return ""
    return urllib.parse.quote(str(text), safe="")


def build_card(repo: dict, username: str) -> str:
    """用 github-readme-stats 生成单个仓库卡片。"""
    name = repo["name"]
    lang = repo.get("language") or "Docs"
    desc = (repo.get("description") or "").strip()
    if len(desc) > 48:
        desc = desc[:45] + "..."

    url = (
        f"https://github-readme-stats.vercel.app/api/pin/"
        f"?username={username}&repo={escape(name)}"
        f"&title_color={CARD_TITLE}&text_color={CARD_TEXT}"
        f"&icon_color={CARD_ICON}&bg_color={CARD_BG}"
        f"&hide_border=true&description_lines=2"
    )
    if desc:
        url += f"&description={escape(desc)}"

    repo_url = f"https://github.com/{username}/{name}"
    star = repo.get("stargazers_count", 0)
    # alt 同时携带语言和 star，方便 SEO / 无图场景
    return (
        f'<a href="{repo_url}">'
        f'<img src="{url}" alt="{escape(name)} - {star} stars - {escape(lang)}" />'
        f"</a>"
    )


def build_section(repos: list, username: str) -> str:
    """拼装卡片网格（2 列）。"""
    cards = [build_card(r, username) for r in repos]
    rows = []
    for i in range(0, len(cards), 2):
        pair = cards[i : i + 2]
        row = "  ".join(pair)
        rows.append(row)
    return "<br/><br/>\n".join(rows)


def update_readme(content: str) -> bool:
    """把生成的区块注入 README 的两个标记之间，返回是否有变更。"""
    try:
        with open(README_FILE, "r", encoding="utf-8") as f:
            readme = f.read()
    except FileNotFoundError:
        print(f"⚠️  找不到 {README_FILE}", file=sys.stderr)
        return False

    start_idx = readme.find(START_MARKER)
    end_idx = readme.find(END_MARKER)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        print(
            f"⚠️  README 中未找到标记区块 {START_MARKER} ... {END_MARKER}，"
            "请先在 README 中添加这两个标记。",
            file=sys.stderr,
        )
        return False

    before = readme[: start_idx + len(START_MARKER)]
    after = readme[end_idx:]
    new_readme = f"{before}\n{content}\n\n{after}"

    if new_readme == readme:
        print("ℹ️  内容无变化，跳过提交。")
        return False

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(new_readme)
    print(f"✅ 已更新 {README_FILE}")
    return True


def main():
    print(f"🔍 拉取 @{USERNAME} 的仓库...")
    repos = fetch_repos(USERNAME)
    print(f"   共 {len(repos)} 个仓库")

    top = select_top_repos(repos, USERNAME, TOP_N)
    if not top:
        print("⚠️  没有符合条件的仓库。")
        return

    print(f"🏆 Top {len(top)} 原创仓库：")
    for r in top:
        print(f"   • {r['name']:30} ⭐{r.get('stargazers_count', 0)}")

    section = build_section(top, USERNAME)
    changed = update_readme(section)
    sys.exit(0 if changed else 0)


if __name__ == "__main__":
    main()
